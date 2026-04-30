from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from api.auth_utils import COOKIE_NAME, SESSION_MAX_AGE_DAYS, create_session, delete_session
from war_room.db import get_db_path

router = APIRouter(prefix="/auth")

# ---------------------------------------------------------------------------
# OAuth routes (ADR-005: Authorization Code + PKCE via authlib)
#
# The OAuth client is initialised in main.py lifespan after load_dotenv()
# and stored in app.state.oauth.  Routes read it from there so that
# GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are resolved after .env is loaded,
# not at module import time.
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    token = await request.app.state.oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo") or {}
    user_id = user_info["sub"]
    user_email = user_info.get("email", "")

    session_id = create_session(get_db_path(), user_id, user_email)

    # Secure flag defaults to False for local dev; set COOKIE_SECURE=true in production.
    secure = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    response = RedirectResponse(url="/")
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    return response


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        delete_session(get_db_path(), session_id)
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie(COOKIE_NAME)
    return response
