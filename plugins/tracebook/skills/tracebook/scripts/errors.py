from __future__ import annotations


class TracebookError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        operation: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.operation = operation
        self.retryable = retryable


class LockTimeoutError(TracebookError):
    def __init__(self, name: str, timeout: float, operation: str) -> None:
        super().__init__(
            "LOCK_TIMEOUT",
            f"Timed out after {timeout:g}s waiting for lock {name}",
            operation,
            retryable=True,
        )


def error_payload(error: TracebookError) -> dict[str, object]:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "operation": error.operation,
            "retryable": error.retryable,
        },
    }
