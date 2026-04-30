from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import router
from war_room.conversation_repository import ConversationRepository
from war_room.db import get_db_path, init_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    db_path = get_db_path()
    init_schema(db_path)
    app.state.repo = ConversationRepository(db_path)
    yield


app = FastAPI(title="war-room", lifespan=lifespan)
app.include_router(router)
