"""Deterministic request budgeting. Never truncate policy, schemas or user text."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
import re
from typing import Any


@lru_cache(maxsize=16)
def _encoding(model: str):
    import tiktoken
    try:
        return tiktoken.encoding_for_model(model.rsplit("/", 1)[-1])
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(value: Any, model: str = "") -> int:
    """Estimate text/protocol tokens; unknown tokenizers remain estimates."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    try:
        return len(_encoding(model).encode(text, disallowed_special=()))
    except (ImportError, ValueError):
        return math.ceil(len(text.encode("utf-8")) / 3)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ContextPolicy:
    name: str
    input_target: int
    schema_budget: int
    output_limit: int
    memory_budget: int = 1000


CHAT = ContextPolicy("chat", 2000, 0, 512, 0)
ORCHESTRATION = ContextPolicy("orchestration", 6000, 1600, 2048)
WORK = ContextPolicy("work", 24000, 3200, 8192, 1600)
REVIEW = ContextPolicy("review", 48000, 4000, 8192, 2400)


def select_policy(prompt: str, role: str = "", *, attachments: bool = False, task_id=None) -> ContextPolicy:
    text = re.sub(r"\s+", " ", prompt.strip().lower()).rstrip("?!. ")
    # Whole-message matching deliberately excludes mixed greetings/action requests.
    if not attachments and not task_id and re.fullmatch(
        r"(?:hi|hello|hey)(?:\s+@?[\w-]+)?|what (?:are your capabilities|can you do)|who are you", text
    ):
        return CHAT
    if any(word in text for word in ("architecture", "audit", "review the", "analyse", "analyze")):
        return REVIEW
    if role.lower() in {"orchestrator", "coordinator"} and not any(
        word in text for word in ("implement", "code", "debug", "fix", "research", "build", "file")
    ):
        return ORCHESTRATION
    return WORK


def tool_name(schema: dict) -> str:
    return schema.get("function", schema).get("name", "")


def provider_schemas(tools: list[dict], provider: str) -> list[dict]:
    declarations = [d for t in tools for d in t.get("functionDeclarations", [t])]
    normalized = []
    for schema in declarations:
        fn = schema.get("function", schema)
        item = {"name": fn["name"], "description": fn.get("description", ""),
                "parameters": fn.get("parameters", fn.get("input_schema", {"type": "object", "properties": {}}))}
        if provider == "anthropic":
            normalized.append({"name": item["name"], "description": item["description"], "input_schema": item["parameters"]})
        elif provider == "google":
            normalized.append(item)
        else:
            if fn.get("strict") is not None:
                item["strict"] = fn["strict"]
            normalized.append({"type": "function", "function": item})
    normalized.sort(key=tool_name)
    return [{"functionDeclarations": normalized}] if provider == "google" and normalized else normalized


def select_schemas(tools: list[dict], budget: int, model: str, required=()) -> list[dict]:
    """Keep whole schemas, discovery and explicitly requested tools. Stable order."""
    if any("functionDeclarations" in t for t in tools):
        declarations = [d for t in tools for d in t.get("functionDeclarations", [])]
        selected = select_schemas(declarations, budget, model, required)
        return [{"functionDeclarations": selected}] if selected else []
    must = set(required) | {"fetch_tool_schemas"}
    selected = [t for t in tools if tool_name(t) in must]
    for schema in tools:
        if schema in selected:
            continue
        if count_tokens(selected + [schema], model) <= budget:
            selected.append(schema)
    return sorted(selected, key=tool_name)


@dataclass(frozen=True)
class ContextPlan:
    model: str
    profile: str
    estimated_tokens: int
    context_window: int
    output_reserve: int
    uncertainty_reserve: int
    input_target: int
    components: dict
    tool_set_hash: str
    prompt_hash: str
    request_hash: str

    def event(self) -> dict:
        return {**asdict(self), "usage_source": "estimated", "usage_percent":
                round(100 * self.estimated_tokens / self.context_window, 1)}


class ContextCapacityError(ValueError):
    pass


def compile_request(system_prompt: str, messages: list, tools: list, *, model: str,
                    context_window: int, policy: ContextPolicy = WORK,
                    max_output: int | None = None) -> ContextPlan:
    # Media is not measured as base64 text. Count a conservative separate reserve.
    media = 0
    def estimate(value):
        nonlocal media
        if isinstance(value, list):
            return [estimate(v) for v in value]
        if isinstance(value, dict):
            if value.get("type") in {"image", "image_url", "input_image"}:
                media += 4096
                return {"type": "image"}
            return {k: estimate(v) for k, v in value.items() if k not in {"created_at", "is_private", "recipient_id"}}
        return value
    measured = estimate(messages)
    components = {"system": count_tokens(system_prompt, model),
                  "tools": count_tokens(tools, model) if tools else 0,
                  "messages": count_tokens(measured, model), "media": media,
                  "protocol": 12 + len(messages) * 8}
    total = sum(components.values())
    margin = max(256, math.ceil(total * 0.05))
    available = context_window - total - margin
    output = min(max_output or policy.output_limit, policy.output_limit, available)
    if output < 64:
        raise ContextCapacityError("Required context leaves no safe output capacity; compact or choose a larger model.")
    return ContextPlan(model, policy.name, total, context_window, output, margin,
                       policy.input_target, components, fingerprint(tools), fingerprint(system_prompt),
                       fingerprint([system_prompt, messages, tools]))


def budget_records(records: list[str], budget: int, query: str, model: str = "") -> str:
    """Rank whole reference records; never cut a fact or promote it to policy."""
    terms = set(re.findall(r"\w{3,}", query.lower()))
    unique = list(dict.fromkeys(records))
    unique.sort(key=lambda r: -len(terms & set(re.findall(r"\w{3,}", r.lower()))))
    result = []
    for record in unique:
        if count_tokens("\n".join(result + [record]), model) <= budget:
            result.append(record)
    return "\n".join(result)
