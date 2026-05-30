from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limiter import (
    login_rate_limit,
    otp_rate_limit,
    register_rate_limit,
)
from app.core.security import (
    COOKIE_ACCESS,
    COOKIE_REFRESH,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    set_auth_cookies,
    verify_password,
)
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import AuditLog, User, UserSession
from app.schemas.auth import (
    AuthSuccessResponse,
    LogoutResponse,
    PasswordLoginRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    RequestEmailOTPRequest,
    RequestSMSOTPRequest,
    TokenMetadata,
    VerificationResponse,
    VerifyEmailRequest,
    VerifyOTPRequest,
    VerifyPhoneRequest,
)
from app.services.notification_service import (
    send_email_otp,
    send_email_verification,
    send_sms_otp,
)
from app.services.otp_service import (
    create_and_store_otp,
    verify_and_consume_otp,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Internal helpers ───────────────────────────────────────────────────────────

def _request_context(request: Request) -> dict:
    return {
        "ip": (
            request.client.host
            if request.client else "unknown"
        ),
        "user_agent": request.headers.get(
            "user-agent", ""
        )[:512],
    }


async def _write_audit(
    db: AsyncSession,
    event: str,
    user_id: str | None,
    request: Request,
    detail: dict | None = None,
) -> None:
    ctx = _request_context(request)
    db.add(AuditLog(
        user_id=user_id,
        event=event,
        ip_address=ctx["ip"],
        user_agent=ctx["user_agent"],
        detail=json.dumps(detail) if detail else None,
    ))


def _assert_account_usable(user: User) -> None:
    """Raise HTTP 403 if the account cannot log in."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_INACTIVE",
                "message": "This account has been deactivated.",
            },
        )
    if not user.is_fully_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_NOT_VERIFIED",
                "message": (
                    "Please verify your email and phone "
                    "number before logging in."
                ),
                "email_verified": user.email_verified,
                "phone_verified": user.phone_verified,
            },
        )


async def _issue_tokens(
    response: Response,
    db: AsyncSession,
    user: User,
    request: Request,
) -> AuthSuccessResponse:
    """
    Common token issuance path for ALL successful login flows.
    Issues access + refresh tokens, persists the hashed session,
    updates last_login_at, and sets HttpOnly cookies.
    """
    access_token,  access_exp  = create_access_token(user.id)
    refresh_token, refresh_exp = create_refresh_token(user.id)

    ctx = _request_context(request)
    db.add(UserSession(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        user_agent=ctx["user_agent"],
        ip_address=ctx["ip"],
        expires_at=refresh_exp,
    ))

    user.last_login_at = datetime.now(timezone.utc)
    set_auth_cookies(response, access_token, refresh_token)
    await _write_audit(db, "login_success", user.id, request)

    return AuthSuccessResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        token_metadata=TokenMetadata(
            access_token_expires_at=access_exp,
            refresh_token_expires_at=refresh_exp,
        ),
    )


# ── Registration ───────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(register_rate_limit),
):
    # Check all unique fields — parameterised queries (no string interpolation)
    for field, value in [
        ("email",    payload.email),
        ("phone",    payload.phone),
        ("username", payload.username),
    ]:
        result = await db.execute(
            select(User).where(
                getattr(User, field) == value
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code":    "DUPLICATE_FIELD",
                    "field":   field,
                    "message": f"This {field} is already registered.",
                },
            )

    user = User(
        email=payload.email,
        phone=payload.phone,
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(
            payload.password.get_secret_value()
        ),
    )
    db.add(user)
    # flush to get user.id before sending notifications
    await db.flush()

    # Generate and dispatch both OTPs
    email_otp = await create_and_store_otp(
        redis, "email_verify", payload.email
    )
    phone_otp = await create_and_store_otp(
        redis, "phone_verify", payload.phone
    )

    await send_email_verification(
        payload.email, payload.full_name, email_otp
    )
    await send_sms_otp(payload.phone, phone_otp)

    await _write_audit(db, "register", user.id, request)
    logger.info("user_registered", user_id=user.id)

    return RegisterResponse(user_id=user.id)


# ── Email verification ─────────────────────────────────────────────────────────

@router.post(
    "/verify/email",
    response_model=VerificationResponse,
    summary="Verify email address via token",
)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
):
    import base64
    try:
        decoded = base64.urlsafe_b64decode(
            payload.token.encode()
        ).decode()
        email, otp = decoded.split(":", 1)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "INVALID_TOKEN",
                "message": "Malformed verification token.",
            },
        )

    valid = await verify_and_consume_otp(
        redis, "email_verify", email, otp
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "INVALID_TOKEN",
                "message": "Token is invalid or has expired.",
            },
        )

    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code":    "USER_NOT_FOUND",
                "message": "User not found.",
            },
        )

    user.email_verified = True
    await _write_audit(db, "email_verified", user.id, request)

    return VerificationResponse(
        verified=True,
        message="Email verified successfully.",
    )


# ── Phone verification ─────────────────────────────────────────────────────────

@router.post(
    "/verify/phone",
    response_model=VerificationResponse,
    summary="Verify phone number via SMS OTP",
)
async def verify_phone(
    payload: VerifyPhoneRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(otp_rate_limit),
):
    valid = await verify_and_consume_otp(
        redis, "phone_verify", payload.phone, payload.otp
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "INVALID_OTP",
                "message": "OTP is invalid or has expired.",
            },
        )

    result = await db.execute(
        select(User).where(User.phone == payload.phone)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code":    "USER_NOT_FOUND",
                "message": "User not found.",
            },
        )

    user.phone_verified = True
    await _write_audit(db, "phone_verified", user.id, request)

    return VerificationResponse(
        verified=True,
        message="Phone number verified successfully.",
    )


# ── Password login ─────────────────────────────────────────────────────────────

@router.post(
    "/login/password",
    response_model=AuthSuccessResponse,
    summary="Login with username/email and password",
)
async def login_password(
    payload: PasswordLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate: None = Depends(login_rate_limit),
):
    identifier = payload.username_or_email
    result = await db.execute(
        select(User).where(
            (User.email == identifier) |
            (User.username == identifier)
        )
    )
    user = result.scalar_one_or_none()

    # Always run bcrypt even if user not found —
    # prevents timing-based user enumeration.
    dummy = "$2b$12$dummyhashfortimingprotectiononly........."
    stored = (
        user.hashed_password
        if (user and user.hashed_password)
        else dummy
    )
    password_ok = verify_password(
        payload.password.get_secret_value(), stored
    )

    if not user or not password_ok:
        await _write_audit(
            db, "login_failed_password",
            user.id if user else None,
            request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_CREDENTIALS",
                "message": "Invalid username or password.",
            },
        )

    _assert_account_usable(user)
    return await _issue_tokens(response, db, user, request)


# ── Email OTP login ────────────────────────────────────────────────────────────

@router.post(
    "/login/otp/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a login OTP via email",
)
async def request_email_otp(
    payload: RequestEmailOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(otp_rate_limit),
):
    """
    Always returns 202 regardless of whether the email exists.
    This prevents email enumeration attacks.
    """
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalar_one_or_none()

    if user and user.email_verified and user.is_active:
        otp = await create_and_store_otp(
            redis, "email_login", payload.email
        )
        await send_email_otp(
            payload.email, user.full_name, otp
        )

    return {
        "message": (
            "If this email is registered, "
            "a login code has been sent."
        )
    }


@router.post(
    "/login/otp/email/verify",
    response_model=AuthSuccessResponse,
    summary="Verify email OTP and issue session",
)
async def verify_email_otp(
    payload: VerifyOTPRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(login_rate_limit),
):
    valid = await verify_and_consume_otp(
        redis, "email_login",
        payload.identifier, payload.otp,
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_OTP",
                "message": "OTP is invalid, expired, or already used.",
            },
        )

    result = await db.execute(
        select(User).where(User.email == payload.identifier)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_OTP",
                "message": "Invalid OTP.",
            },
        )

    _assert_account_usable(user)
    return await _issue_tokens(response, db, user, request)


# ── SMS OTP login ──────────────────────────────────────────────────────────────

@router.post(
    "/login/otp/sms/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a login OTP via SMS",
)
async def request_sms_otp(
    payload: RequestSMSOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(otp_rate_limit),
):
    """Always returns 202 to prevent phone number enumeration."""
    result = await db.execute(
        select(User).where(User.phone == payload.phone)
    )
    user = result.scalar_one_or_none()

    if user and user.phone_verified and user.is_active:
        otp = await create_and_store_otp(
            redis, "sms_login", payload.phone
        )
        await send_sms_otp(payload.phone, otp)

    return {
        "message": (
            "If this number is registered, "
            "a login code has been sent."
        )
    }


@router.post(
    "/login/otp/sms/verify",
    response_model=AuthSuccessResponse,
    summary="Verify SMS OTP and issue session",
)
async def verify_sms_otp(
    payload: VerifyOTPRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(login_rate_limit),
):
    valid = await verify_and_consume_otp(
        redis, "sms_login",
        payload.identifier, payload.otp,
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_OTP",
                "message": "OTP is invalid, expired, or already used.",
            },
        )

    result = await db.execute(
        select(User).where(User.phone == payload.identifier)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_OTP",
                "message": "Invalid OTP.",
            },
        )

    _assert_account_usable(user)
    return await _issue_tokens(response, db, user, request)


# ── Google OAuth ───────────────────────────────────────────────────────────────

@router.get(
    "/login/google",
    summary="Initiate Google OAuth flow",
)
async def google_login(response: Response):
    """
    Returns the Google authorisation URL.
    The frontend redirects the browser to this URL.
    A CSRF state token is stored in a short-lived HttpOnly cookie.
    """
    state = secrets.token_urlsafe(32)
    response.set_cookie(
        "oauth_state", state,
        max_age=300,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    async with AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        scope="openid email profile",
    ) as client:
        uri, _ = client.create_authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            state=state,
            access_type="offline",
        )
    return {"auth_url": uri}


@router.get(
    "/google/callback",
    response_model=AuthSuccessResponse,
    summary="Google OAuth callback",
)
async def google_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth_state: Annotated[str | None, Cookie()] = None,
):
    # CSRF validation — compare state param with cookie value
    if not oauth_state or not secrets.compare_digest(
        state, oauth_state
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "INVALID_STATE",
                "message": "OAuth state mismatch. Possible CSRF attack.",
            },
        )
    response.delete_cookie("oauth_state")

    # Exchange code for tokens and fetch user info
    async with AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    ) as client:
        await client.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code,
        )
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo"
        )
        userinfo = userinfo_resp.json()

    google_sub = userinfo["sub"]
    email      = userinfo.get("email", "").lower()
    name       = userinfo.get("name", "")

    # Find existing user by google_sub or email
    result = await db.execute(
        select(User).where(
            (User.google_sub == google_sub) |
            (User.email == email)
        )
    )
    user = result.scalar_one_or_none()

    if user:
        # Link Google account if not already linked
        if not user.google_sub:
            user.google_sub = google_sub
        if not user.email_verified:
            user.email_verified = True
    else:
        # Auto-create account for new Google users
        user = User(
            email=email,
            phone="",
            username=f"g_{google_sub[:20]}",
            full_name=name,
            google_sub=google_sub,
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        await _write_audit(
            db, "register_google", user.id, request
        )

    _assert_account_usable(user)
    return await _issue_tokens(response, db, user, request)


# ── Token refresh ──────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Rotate access and refresh tokens",
)
async def refresh_tokens(
    response: Response,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[
        str | None, Cookie(alias=COOKIE_REFRESH)
    ] = None,
):
    """
    Silent token rotation — called by the frontend 2 minutes
    before the access token expires (see useTokenRefresh hook).

    Refresh token rotation:
      - Old session row is marked is_valid=False.
      - New session row is inserted.
      - If the old token is presented again (reuse attack),
        ALL sessions for that user are immediately invalidated.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "NO_TOKEN",
                "message": "Not authenticated.",
            },
        )

    try:
        payload = decode_refresh_token(refresh_token)
    except JWTError:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_TOKEN",
                "message": "Refresh token is invalid.",
            },
        )

    user_id    = payload["sub"]
    token_hash = hash_token(refresh_token)

    # Validate session in DB
    result = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.is_valid   == True,
            UserSession.user_id    == user_id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        # Token reuse detected — invalidate ALL user sessions
        all_sessions = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        )
        for s in all_sessions.scalars().all():
            s.is_valid = False

        clear_auth_cookies(response)
        await _write_audit(
            db, "refresh_token_reuse_detected",
            user_id, request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "SESSION_INVALID",
                "message": "Session has been revoked.",
            },
        )

    # Fetch user
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "ACCOUNT_INACTIVE",
                "message": "Account is inactive.",
            },
        )

    # Rotate tokens
    session.is_valid = False
    new_access,  access_exp  = create_access_token(user_id)
    new_refresh, refresh_exp = create_refresh_token(user_id)

    ctx = _request_context(request)
    db.add(UserSession(
        user_id=user_id,
        token_hash=hash_token(new_refresh),
        user_agent=ctx["user_agent"],
        ip_address=ctx["ip"],
        expires_at=refresh_exp,
    ))

    set_auth_cookies(response, new_access, new_refresh)

    return RefreshResponse(
        access_token_expires_at=access_exp
    )


# ── Logout ─────────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Invalidate session and clear cookies",
)
async def logout(
    response: Response,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[
        str | None, Cookie(alias=COOKIE_REFRESH)
    ] = None,
):
    if refresh_token:
        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(UserSession).where(
                UserSession.token_hash == token_hash
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.is_valid = False
            await _write_audit(
                db, "logout", session.user_id, request
            )

    clear_auth_cookies(response)
    return LogoutResponse()


# ── Current user ───────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=AuthSuccessResponse,
    summary="Get current authenticated user",
)
async def get_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[
        str | None, Cookie(alias=COOKIE_ACCESS)
    ] = None,
):
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "NOT_AUTHENTICATED",
                "message": "Not authenticated.",
            },
        )
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code":    "INVALID_TOKEN",
                "message": "Invalid or expired token.",
            },
        )

    result = await db.execute(
        select(User).where(User.id == payload["sub"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code":    "USER_NOT_FOUND",
                "message": "User not found.",
            },
        )

    now = datetime.now(timezone.utc)
    return AuthSuccessResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        token_metadata=TokenMetadata(
            access_token_expires_at=now + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            ),
            refresh_token_expires_at=now + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            ),
        ),
    )
