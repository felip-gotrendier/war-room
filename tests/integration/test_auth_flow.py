"""OAuth flow integration tests.

These tests require real Google OAuth credentials and network access.
They are automatically skipped in CI and dev environments without credentials.

For full empirical validation, see Phase 2b.1 verification procedure:
  1. Start server: uvicorn api.main:app --reload
  2. Open http://localhost:8000/auth/login in a browser
  3. Complete Google OAuth flow with a real account
  4. Verify war_room_session cookie is set (HTTP-only)
  5. Verify sessions row in war-room.db: sqlite3 war-room.db "SELECT * FROM sessions"
  6. Open http://localhost:8000/auth/logout — verify cookie is cleared

Run with real credentials:
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... OAUTH_REDIRECT_URI=... \
    pytest tests/integration/test_auth_flow.py -v -s
"""
from __future__ import annotations

import os

import pytest


def _oauth_creds_set() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")
    )


skip_if_no_oauth = pytest.mark.skipif(
    not _oauth_creds_set(),
    reason="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not set — skipping OAuth integration tests",
)


@skip_if_no_oauth
def test_placeholder_oauth_creds_present():
    """Placeholder: confirms credentials are present when skip guard is lifted.

    Real OAuth route tests (login redirect, callback exchange, logout) require
    either a mock OAuth server or browser automation. Both are out of scope for
    Phase 2b.1. Empirical validation is done manually per the procedure above.
    """
    assert os.environ.get("GOOGLE_CLIENT_ID")
    assert os.environ.get("GOOGLE_CLIENT_SECRET")
