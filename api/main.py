from __future__ import annotations

# Load .env before any module-level code that reads os.environ
# (includes orchestrator._client, _session_secret below, and OAuth registration).
from dotenv import load_dotenv
load_dotenv()

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from api.auth import router as auth_router
from api.routes import router
from api.ui_routes import router as ui_router
from war_room.conversation_repository import ConversationRepository
from war_room.db import get_db_path, init_schema
from war_room.saved_investigation_repository import SavedInvestigationRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    # SQLite: schema + repository
    db_path = get_db_path()
    init_schema(db_path)
    app.state.repo = ConversationRepository(db_path)
    app.state.saved_inv_repo = SavedInvestigationRepository(db_path)

    # OAuth client (ADR-005: Authorization Code + PKCE via authlib)
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",  # PKCE (ADR-005)
        },
    )
    app.state.oauth = oauth

    yield


# SessionMiddleware signs the ephemeral OAuth dance cookie (state + code_verifier).
# This is separate from the long-lived war_room_session cookie managed by auth_utils.
# SESSION_SECRET_KEY is read here (after load_dotenv() above) so .env values are
# picked up.  If not set, a random key is generated per process — acceptable for
# dev (OAuth dance state is lost on restart), not for production.
_session_secret = os.environ.get("SESSION_SECRET_KEY") or secrets.token_hex(32)

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="war-room", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
app.include_router(auth_router)
app.include_router(router)
app.include_router(ui_router)
