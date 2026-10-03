"""Safe provider diagnostics expose status and allowlisted codes, never payloads."""

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError

_SAFE_CODES = frozenset(
    {
        "invalid_api_key",
        "model_not_found",
        "insufficient_quota",
        "rate_limit_exceeded",
        "invalid_json_schema",
        "unsupported_parameter",
        "permission_denied",
    }
)


def safe_api_failure(error: APIError) -> str:
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, APIConnectionError):
        return "connection failure"
    if isinstance(error, APIStatusError):
        detail = f"HTTP {error.status_code}"
        if isinstance(error.code, str) and error.code in _SAFE_CODES:
            detail += f"; {error.code}"
        return detail
    return "provider failure"
