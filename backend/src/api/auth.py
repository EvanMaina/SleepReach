"""
Authentication endpoints: login, logout, me, change-password, forgot-password, reset-password.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from ..core.database import get_db
from ..core.config import settings
from ..core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
)
from ..core.auth import get_current_user
from ..models.user import User, UserStatus, PasswordResetToken, get_permissions_for_role
from ..schemas.user import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ValidateResetTokenResponse,
    MeResponse,
)
from pydantic import BaseModel, EmailStr, Field


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Password complexity requirements
PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\\/~`])[A-Za-z\d!@#$%^&*(),.?":{}|<>\-_=+\[\]\\\/~`]{8,}$'
)

# Rate limiting for forgot password
RESET_TOKEN_EXPIRY_HOURS = 1
RESET_RATE_LIMIT_PER_HOUR = 5


def _validate_password_strength(password: str) -> None:
    """Validate password meets complexity requirements. Raises HTTPException if not."""
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\\/~`]', password):
        errors.append("Password must contain at least one special character")
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors),
        )


def _hash_token(token: str) -> str:
    """Hash a reset token for secure storage using SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# =============================================================================
# Login
# =============================================================================


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Authenticate with email + password.  Returns JWT access + refresh tokens.
    Checks temporary password expiry for invited users.
    """
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        # Log failed login attempt
        logger.warning(
            f"Failed login attempt for email={credentials.email} "
            f"ip={request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.INACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated. Contact your administrator.",
        )

    # Check if temporary password has expired (48-hour window)
    if user.must_change_password and user.password_expires_at:
        if datetime.now(timezone.utc) > user.password_expires_at:
            logger.warning(f"Expired temporary password used for {user.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your temporary password has expired. Please ask your administrator to resend the invitation.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Update last_login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
        must_change_password=user.must_change_password,
    )


# =============================================================================
# Refresh Token
# =============================================================================


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh"""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """Response body for token refresh"""
    access_token: str
    refresh_token: str


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> RefreshTokenResponse:
    """
    Refresh an access token using a valid refresh token.
    Returns a new access token and refresh token.
    """
    # Decode and validate the refresh token
    payload = decode_token(body.refresh_token)
    
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch the user
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
    
    # Generate new tokens
    token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data=token_data)
    
    logger.info(f"Token refreshed for user {user.email}")
    
    return RefreshTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


# =============================================================================
# Current User
# =============================================================================


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user)) -> MeResponse:
    """Return the authenticated user's profile and permission set."""
    return MeResponse(
        user=UserResponse.model_validate(user),
        permissions=get_permissions_for_role(user.role),
    )


# =============================================================================
# Change Password
# =============================================================================


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    """
    Change the current user's password.

    On first login (must_change_password == True) the current_password field
    is not required.  After that it is mandatory.
    """
    if not user.must_change_password:
        # Normal password change — require current password
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    # Validate password strength
    _validate_password_strength(body.new_password)

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_expires_at = None  # Clear expiry after password change
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    db.commit()

    return ChangePasswordResponse(success=True, message="Password updated successfully")


# =============================================================================
# Logout
# =============================================================================


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    """
    Logout endpoint.  Tokens are stateless so the client simply discards them.
    """
    return {"success": True, "message": "Logged out successfully"}


# =============================================================================
# Forgot Password — Request a reset link
# =============================================================================


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> ForgotPasswordResponse:
    """
    Request a password reset link.  Always returns success for security
    (don't reveal whether the email exists).  Rate-limited to 5 per hour per email.
    """
    # Always return the same message regardless of whether user exists (security)
    safe_message = "If an account exists with this email, you'll receive a reset link."

    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        logger.info(f"Password reset requested for unknown email: {body.email}")
        return ForgotPasswordResponse(success=True, message=safe_message)

    if user.status == UserStatus.INACTIVE:
        logger.info(f"Password reset requested for inactive user: {body.email}")
        return ForgotPasswordResponse(success=True, message=safe_message)

    # Rate limiting: max 5 tokens per hour per user
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_count = (
        db.query(sa_func.count(PasswordResetToken.id))
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= one_hour_ago,
        )
        .scalar()
    )
    if recent_count >= RESET_RATE_LIMIT_PER_HOUR:
        logger.warning(f"Rate limit hit for password reset: {body.email}")
        return ForgotPasswordResponse(success=True, message=safe_message)

    # Generate cryptographically secure token
    raw_token = generate_secure_token(48)
    token_hash = _hash_token(raw_token)

    # Store hashed token with 1-hour expiry
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS),
    )
    db.add(reset_token)
    db.commit()

    # Build reset URL — prefer the first non-localhost, non-API CORS origin
    frontend_url = "http://localhost:5173"
    cors_origins = getattr(settings, 'cors_origins', '')
    for origin in cors_origins.split(','):
        origin = origin.strip()
        if origin and origin != '*' and 'localhost' not in origin and 'api.' not in origin:
            frontend_url = origin
            break

    reset_url = f"{frontend_url}/#reset-password?token={raw_token}"

    # Send reset email (best-effort) — routes through Paubox when EMAIL_MODE=paubox
    try:
        from ..services.email_service import EmailService
        from ..services.paubox_email_service import send_email_via_paubox

        email_svc = EmailService()
        html = email_svc.render_template("password_reset", {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "reset_url": reset_url,
        })
        text_content = (
            f"Hi {user.first_name},\n\n"
            f"We received a request to reset your password for your TMS NeuroReach account.\n\n"
            f"Click the link below to reset your password:\n{reset_url}\n\n"
            f"This link will expire in 1 hour.\n\n"
            f"If you didn't request this, you can safely ignore this email.\n\n"
            f"— TMS Institute of Arizona Team"
        )
        result = send_email_via_paubox(
            to_email=user.email,
            subject="Password Reset Request — TMS NeuroReach",
            html_content=html,
            text_content=text_content,
        )
        if result.get("success"):
            logger.info(f"Password reset email sent to {user.email} via {result.get('provider', 'unknown')}")
        else:
            logger.error(f"Password reset email failed for {user.email}: {result.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {e}")

    return ForgotPasswordResponse(success=True, message=safe_message)


# =============================================================================
# Validate Reset Token — Check if a token is still valid
# =============================================================================


@router.get("/validate-reset-token", response_model=ValidateResetTokenResponse)
async def validate_reset_token(
    token: str,
    db: Session = Depends(get_db),
) -> ValidateResetTokenResponse:
    """
    Validate a password reset token without consuming it.
    Used by the frontend to check if the reset link is still valid.
    """
    token_hash = _hash_token(token)
    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if not reset_token:
        return ValidateResetTokenResponse(valid=False, message="Invalid or expired reset link.")

    if reset_token.is_used:
        return ValidateResetTokenResponse(valid=False, message="This reset link has already been used.")

    if reset_token.is_expired:
        return ValidateResetTokenResponse(valid=False, message="This reset link has expired. Please request a new one.")

    return ValidateResetTokenResponse(valid=True, message="Token is valid.")


# =============================================================================
# Reset Password — Set new password using a valid token
# =============================================================================


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> ResetPasswordResponse:
    """
    Reset the user's password using a valid, unexpired, unused token.
    The token is invalidated (one-time use) after successful reset.
    """
    token_hash = _hash_token(body.token)
    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link.",
        )

    if reset_token.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used. Please request a new one.",
        )

    if reset_token.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    # Validate password strength
    _validate_password_strength(body.new_password)

    # Update the user's password
    user = reset_token.user
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_expires_at = None
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE

    # Invalidate the token (one-time use)
    reset_token.used_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Password reset successfully for {user.email}")

    return ResetPasswordResponse(
        success=True,
        message="Your password has been reset. You can now log in with your new password.",
    )


# =============================================================================
# Request Access — Public endpoint for requesting dashboard access
# =============================================================================


class AccessRequestBody(BaseModel):
    """Request body for access request."""
    full_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    reason: str = Field(..., min_length=5, max_length=1000)


class AccessRequestResponse(BaseModel):
    success: bool
    message: str


@router.post("/request-access", response_model=AccessRequestResponse)
async def request_access(
    body: AccessRequestBody,
    db: Session = Depends(get_db),
) -> AccessRequestResponse:
    """
    Public endpoint: submit a request for dashboard access.
    Sends a notification email to ALL admin users so they can manually create the account.
    """
    logger.info(f"Access request received from {body.full_name} <{body.email}>")

    # Query ALL admin/primary_admin users from database
    from ..models.user import UserRole
    admin_users = (
        db.query(User)
        .filter(
            User.role.in_([UserRole.ADMINISTRATOR, UserRole.PRIMARY_ADMIN]),
            User.status == UserStatus.ACTIVE,
        )
        .all()
    )

    # Build list of admin emails; fall back to from_email if no admins found
    admin_emails = [u.email for u in admin_users if u.email]
    if not admin_emails:
        fallback = getattr(settings, 'from_email', 'noreply@neuroreach.ai')
        admin_emails = [fallback]

    logger.info(f"Sending access request notification to {len(admin_emails)} admin(s): {admin_emails}")

    # Send notification email to EACH admin — routes through Paubox when EMAIL_MODE=paubox
    try:
        from ..services.email_service import EmailService
        from ..services.paubox_email_service import send_email_via_paubox

        email_svc = EmailService()
        html = email_svc.render_template("access_request_admin", {
            "full_name": body.full_name,
            "requester_email": body.email,
            "reason": body.reason,
        })
        text_content = (
            f"New Access Request — TMS NeuroReach\n\n"
            f"A new user has requested access to the TMS NeuroReach dashboard:\n\n"
            f"Name: {body.full_name}\n"
            f"Email: {body.email}\n"
            f"Role/Reason: {body.reason}\n\n"
            f"To grant access, log into the admin panel and create their account.\n"
        )

        for admin_email in admin_emails:
            try:
                result = send_email_via_paubox(
                    to_email=admin_email,
                    subject="New Access Request — TMS NeuroReach",
                    html_content=html,
                    text_content=text_content,
                )
                if result.get("success"):
                    logger.info(f"Access request notification sent to {admin_email} via {result.get('provider', 'unknown')} for {body.email}")
                else:
                    logger.error(f"Access request notification failed for {admin_email}: {result.get('error', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to send access request notification to {admin_email}: {e}")

    except Exception as e:
        logger.error(f"Failed to send access request notifications: {e}")

    return AccessRequestResponse(
        success=True,
        message="Your request has been submitted. An administrator will review it and send you an invitation.",
    )
