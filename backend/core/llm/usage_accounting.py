"""Provider usage normalization; cached/reasoning subsets are never counted twice."""
from dataclasses import asdict, dataclass


def nonnegative(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = int(value)
        return n if n >= 0 and n == float(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    input_source: str
    output_source: str

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self):
        return {**asdict(self), "total_tokens": self.total_tokens,
                "usage_source": "provider" if self.input_source == self.output_source == "provider" else "estimated"}


def normalize_usage(raw: dict | None, estimated_input: int = 0, estimated_output: int = 0) -> Usage:
    raw = raw if isinstance(raw, dict) else {}
    input_details = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    output_details = raw.get("completion_tokens_details") or raw.get("output_tokens_details") or {}
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = output_details if isinstance(output_details, dict) else {}
    reads = nonnegative(raw.get("cache_read_input_tokens", input_details.get("cached_tokens")))
    writes = nonnegative(raw.get("cache_creation_input_tokens"))
    prompt = nonnegative(raw.get("prompt_tokens"))
    if prompt is None:
        prompt = nonnegative(raw.get("input_tokens"))
        if prompt is not None and ("cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw):
            if (("cache_read_input_tokens" in raw and reads is None)
                    or ("cache_creation_input_tokens" in raw and writes is None)):
                prompt = None
            else:
                prompt += (reads or 0) + (writes or 0)
    completion = nonnegative(raw.get("completion_tokens", raw.get("output_tokens")))
    return Usage(prompt if prompt is not None else estimated_input,
                 completion if completion is not None else estimated_output, reads, writes,
                 nonnegative(output_details.get("reasoning_tokens")),
                 "provider" if prompt is not None else "estimated",
                 "provider" if completion is not None else "estimated")
