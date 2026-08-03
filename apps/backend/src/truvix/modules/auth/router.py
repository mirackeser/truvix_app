"""HTTP endpoints for registration, sign-in and session management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status

from truvix.modules.auth.dependencies import AuthServiceDep, CurrentUserDep, SessionContextDep
from truvix.modules.auth.schemas import (
    AuthenticatedResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegistrationRequest,
    TokenPairResponse,
    UserResponse,
)
from truvix.modules.auth.service import AuthenticatedSession
from truvix.shared.errors import PROBLEM_CONTENT_TYPE
from truvix.shared.ratelimit import enforce_auth_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

_PROBLEM_RESPONSE: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}

_AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Credentials rejected.", **_PROBLEM_RESPONSE},
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "Too many attempts from this client.",
        **_PROBLEM_RESPONSE,
    },
}


def _to_response(session: AuthenticatedSession) -> AuthenticatedResponse:
    """Map an authenticated session onto its wire representation."""
    return AuthenticatedResponse(
        user=UserResponse.from_user(session.user),
        tokens=TokenPairResponse(
            access_token=session.access_token.value,
            refresh_token=session.refresh_token.value,
            expires_in=session.access_token_ttl_seconds,
        ),
    )


@router.post(
    "/register",
    response_model=AuthenticatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description="Registers a new account and returns its first token pair.",
    dependencies=[Depends(enforce_auth_rate_limit)],
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "Email address or phone number already registered.",
            **_PROBLEM_RESPONSE,
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Too many attempts from this client.",
            **_PROBLEM_RESPONSE,
        },
    },
)
async def register(
    payload: RegistrationRequest,
    service: AuthServiceDep,
    context: SessionContextDep,
) -> AuthenticatedResponse:
    """Register a new account."""
    session = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        context=context,
    )
    return _to_response(session)


@router.post(
    "/login",
    response_model=AuthenticatedResponse,
    summary="Sign in",
    description="Exchanges an email address and password for a token pair.",
    dependencies=[Depends(enforce_auth_rate_limit)],
    responses=_AUTH_ERROR_RESPONSES,
)
async def login(
    payload: LoginRequest,
    service: AuthServiceDep,
    context: SessionContextDep,
) -> AuthenticatedResponse:
    """Authenticate an account and start a session."""
    session = await service.authenticate(
        email=payload.email,
        password=payload.password,
        context=context,
    )
    return _to_response(session)


@router.post(
    "/refresh",
    response_model=AuthenticatedResponse,
    summary="Rotate a session",
    description=(
        "Exchanges a refresh token for a new pair. The presented token is "
        "invalidated; replaying it revokes every session for the account."
    ),
    dependencies=[Depends(enforce_auth_rate_limit)],
    responses=_AUTH_ERROR_RESPONSES,
)
async def refresh(
    payload: RefreshRequest,
    service: AuthServiceDep,
    context: SessionContextDep,
) -> AuthenticatedResponse:
    """Rotate a refresh token into a new pair."""
    session = await service.refresh(refresh_token=payload.refresh_token, context=context)
    return _to_response(session)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out of one session",
    description="Invalidates the supplied refresh token.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token could not be read.",
            **_PROBLEM_RESPONSE,
        }
    },
)
async def logout(payload: LogoutRequest, service: AuthServiceDep) -> None:
    """End the session identified by the supplied refresh token."""
    await service.logout(refresh_token=payload.refresh_token)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out everywhere",
    description="Invalidates every session belonging to the authenticated account.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Access token missing or invalid.",
            **_PROBLEM_RESPONSE,
        }
    },
)
async def logout_everywhere(current_user: CurrentUserDep, service: AuthServiceDep) -> None:
    """End every session for the authenticated account."""
    await service.logout_everywhere(user_id=current_user.id)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current account",
    description="Returns the account behind the supplied access token.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Access token missing or invalid.",
            **_PROBLEM_RESPONSE,
        }
    },
)
async def read_current_user(current_user: CurrentUserDep) -> UserResponse:
    """Return the authenticated account."""
    return UserResponse.from_user(current_user)
