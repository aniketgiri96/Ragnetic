"""KnowAI FastAPI application."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import auth, deps, routes
from app.models.init_db import init_db


class ChatRequest(BaseModel):
    message: str
    kb_id: Optional[int] = None
    session_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="KnowAI",
    description="Open-Source RAG Knowledge Base Platform API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/")
async def root():
    return await routes.root()


@app.post("/upload/")
async def upload_document(
    file: UploadFile = File(...),
    kb_id: int = Query(None),
    _user=Depends(deps.get_current_user),
):
    return await routes.upload_document(file, kb_id)


@app.get("/search/")
async def search_documents(query: str, kb_id: int = Query(None)):
    return await routes.search_documents(query, kb_id)


@app.post("/chat/")
async def chat_endpoint(body: ChatRequest):
    return await routes.chat_rag(
        message=body.message,
        kb_id=body.kb_id,
        session_id=body.session_id,
    )


@app.get("/kb/", response_model=list)
def list_kb():
    return routes.list_knowledge_bases()


@app.get("/documents/{document_id}/status")
def document_status(document_id: int):
    out = routes.get_document_status(document_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return out
