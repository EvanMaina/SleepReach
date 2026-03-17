"""
Authentication and authorisation dependencies for FastAPI routes.

Provides:
- get_current_user: extracts & verifies JWT, returns the User row
- require_role(*roles): factory that returns a dependency enforcing role membership
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .security import decode_token
from ..models.user import User, UserRole, UserStatus


logger = logging.getLogger(__name__)

# The tokenUrl is informational (used by Swagger UI); actual login is POST /api/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the JWT bearer token and return the authenticated User.

    Raises 401 if token is missing, invalid, or the user is inactive.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.INACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    return user


# Role hierarchy: primary_admin implicitly satisfies "administrator" checks.
_ROLE_IMPLIES: dict[str, set[str]] = {
    "primary_admin": {"primary_admin", "administrator"},
    "administrator": {"administrator"},
    "coordinator": {"coordinator"},
    "specialist": {"specialist"},
}


def require_role(*allowed_roles: str):
    """
    Factory: returns a FastAPI dependency that checks the current user's role.

    primary_admin is treated as a superset of administrator -- any endpoint
    that requires "administrator" will also accept "primary_admin".

    Usage:
        @router.delete("/{id}", dependencies=[Depends(require_role("administrator"))])
    """
    async def _check(user: User = Depends(get_current_user)) -> User:
        effective_roles = _ROLE_IMPLIES.get(user.role.value, {user.role.value})
        if not effective_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return _check
