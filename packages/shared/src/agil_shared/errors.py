from uuid import uuid4


class DomainError(Exception):
    """Error seguro que puede cruzar la frontera HTTP sin secretos."""

    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.status_code = status
        self.retryable = retryable

    def as_dict(self, correlation_id: str | None = None) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable,
                "correlation_id": correlation_id or str(uuid4())}
