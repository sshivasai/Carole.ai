"""Rank registered tool descriptions, without granting permission to execute them."""
from functools import lru_cache
import logging
import re
import threading

import numpy as np

from core.knowledge.hybrid_search import StaticCodeEmbedder

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_STOP_WORDS = set("a an and are as at be by can could do for from how i in is it me of on or please that the this to use with you your".split())


def _terms(text):
    return set(re.findall(r"[^\W_]+", text.casefold())) - _STOP_WORDS


def _document(spec):
    purpose = re.split(r"(?<=[.!?])\s+|\n", spec.description.strip())[0][:400]
    return f"{spec.name.replace('_', ' ')}. {purpose}"


@lru_cache(maxsize=8)
def _vectors(model, documents):
    values = np.asarray(model.encode(list(documents)), dtype=float)
    if values.ndim != 2 or values.shape[0] != len(documents) or not np.isfinite(values).all():
        raise ValueError("Invalid tool embeddings")
    return values / np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-10)


@lru_cache(maxsize=128)
def _query_vector(model, query):
    return _vectors.__wrapped__(model, (query,))[0]


def rank_tools(query, specs):
    """Return relevant names in order; fall back to whole-word retrieval on outages.

    Callers must supply only visible tools. Metadata is encoded as data, never
    promoted into instructions. Registry changes naturally change cache keys.
    """
    query = re.sub(r"@[\w-]+", "", (query or "")).strip()[:4000]
    specs = sorted(specs, key=lambda spec: spec.name)
    if not query or not specs:
        return []
    documents = tuple(_document(spec) for spec in specs)
    terms = _terms(query)
    lexical = [len(terms & _terms(doc)) / max(len(terms), 1) for doc in documents]
    scores = lexical
    try:
        with _lock:
            model = StaticCodeEmbedder.get_model()
            if model is not None:
                clauses = [part.strip() for part in re.split(r"[;?!]|\band\b|\bthen\b", query, flags=re.I)
                           if len(_terms(part)) >= 3]
                queries = list(dict.fromkeys([query] + clauses))[:8]
                query_vectors = np.asarray([_query_vector(model, part) for part in queries])
                similarities = (_vectors(model, documents) @ query_vectors.T).max(axis=1)
                scores = [0.85 * max(float(sim), 0.0) + 0.15 * lex
                          for sim, lex in zip(similarities, lexical)]
    except Exception as exc:
        logger.warning("Semantic tool retrieval unavailable; using description search: %s", type(exc).__name__)
    explicit = set(re.findall(r"\b[\w-]+\b", query.casefold()))
    remaining = [(spec, 2.0 if spec.name.casefold() in explicit else score)
                 for spec, score in zip(specs, scores) if score > 0.12 or spec.name.casefold() in explicit]
    ranked, counts = [], {}
    while remaining:
        # Avoid letting a large family crowd every other capability out of a compound request.
        spec, score = min(remaining, key=lambda item: (
            -item[1] / (1 + 0.35 * counts.get(item[0].category, 0)), item[0].name))
        remaining.remove((spec, score))
        ranked.append(spec.name)
        counts[spec.category] = counts.get(spec.category, 0) + 1
    return ranked


def discover_tools(args, specs):
    """Shared matching for discovery output and subsequent schema activation."""
    names = args.get("tool_names") or args.get("tool_name") or []
    names = [names] if isinstance(names, str) else names
    names = [name.strip() for name in names if isinstance(name, str)]
    family = (args.get("family") or args.get("category") or "").casefold().strip()
    query = (args.get("query") or "").strip()
    available = {spec.name: spec for spec in specs}
    candidates = [spec for spec in specs if not family or spec.category.casefold() == family]
    ranked = rank_tools(query, candidates) if query else [spec.name for spec in candidates]
    requested = list(dict.fromkeys(names + (ranked if family or query else [])))
    return [available[name] for name in requested if name in available]


def catalog_summary(specs, max_chars=5000):
    """Retain every family even when a large plugin catalog needs summarizing."""
    families = {}
    for spec in specs:
        families.setdefault(spec.category, []).append(spec)
    lines = ["Permitted families: " + ", ".join(sorted(families)),
             "Search any permitted tool by purpose with fetch_tool_schemas(query=...)."]
    for category, members in sorted(families.items()):
        examples = "; ".join(f"{spec.name}: {spec.description.splitlines()[0][:70]}" for spec in members[:3])
        line = f"- {category} ({len(members)} tools): {examples}"
        if len("\n".join(lines + [line])) <= max_chars:
            lines.append(line)
    return "\n".join(lines)
