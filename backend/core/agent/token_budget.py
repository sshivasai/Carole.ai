"""Validate provider accounting without turning malformed usage into a model retry."""
def reported_total(usage: dict) -> int | None:
    def count(value):
        if isinstance(value, bool):
            raise ValueError("Boolean usage")
        result = int(value)
        if result < 0 or (isinstance(value, float) and value != result):
            raise ValueError("Invalid token count")
        return result
    try:
        total = count(usage.get("prompt_tokens", usage.get("input_tokens")))
        total += count(usage.get("completion_tokens", usage.get("output_tokens")))
        if "input_tokens" in usage and "prompt_tokens" not in usage:
            total += count(usage.get("cache_read_input_tokens", 0))
            total += count(usage.get("cache_creation_input_tokens", 0))
        return total
    except (ValueError, TypeError, OverflowError):
        return None
