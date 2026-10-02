"""Contract-shaped API errors: {"error": {"code": ..., "message": ...}}."""

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
    )


def unauthenticated() -> ApiError:
    # Same response for bad credentials, missing/expired sessions, and
    # inactive accounts: callers learn nothing about which check failed.
    return ApiError("UNAUTHENTICATED", "Authentication is required.", 401)


def forbidden(message: str = "You do not have permission for this action.") -> ApiError:
    return ApiError("FORBIDDEN", message, 403)


def lab_not_found() -> ApiError:
    # Used for every lab a caller may not see (missing, inactive, or simply
    # not a member) so membership cannot be probed.
    return ApiError("LAB_NOT_FOUND", "The requested lab was not found.", 404)


def device_not_found() -> ApiError:
    # Same masking rule as labs: missing, inactive-lab, or simply
    # not visible to the caller all read as "not found".
    return ApiError("DEVICE_NOT_FOUND", "The requested device was not found.", 404)
