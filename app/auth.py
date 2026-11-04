import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import load_api_keys


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_key(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized("Missing or malformed Authorization header")

    token = authorization[len("Bearer "):].strip()
    for valid in load_api_keys():
        if hmac.compare_digest(token.encode(), valid.encode()):
            return token

    raise _unauthorized("Invalid API key")