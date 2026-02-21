"""Ragnetic FastAPI application."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from app.api import auth, deps, routes
from app.core.config import validate_security_settings
from app.models.init_db import init_db
from app.services.rate_limit import enforce_rate_limit


class ChatRequest(BaseModel):
    message: str
    kb_id: Optional[int] = None
    session_id: Optional[str] = None


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_settings()
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Ragnetic",
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
    request: Request,
    file: UploadFile = File(...),
    kb_id: int = Query(None),
    user=Depends(deps.get_current_user),
):
    ip = request.client.host if request and request.client else "unknown"
    enforce_rate_limit("upload", key=f"user:{user.id}:ip:{ip}")
    return await routes.upload_document(user=user, file=file, kb_id=kb_id)


@app.get("/search/")
async def search_documents(
    request: Request,
    query: str,
    kb_id: int = Query(None),
    user=Depends(deps.get_current_user),
):
    ip = request.client.host if request and request.client else "unknown"
    enforce_rate_limit("search", key=f"user:{user.id}:ip:{ip}")
    return await routes.search_documents(user=user, query=query, kb_id=kb_id)


@app.post("/chat/")
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    user=Depends(deps.get_current_user),
):
    ip = request.client.host if request and request.client else "unknown"
    enforce_rate_limit("chat", key=f"user:{user.id}:ip:{ip}")
    return await routes.chat_rag(
        user=user,
        message=body.message,
        kb_id=body.kb_id,
        session_id=body.session_id,
    )


@app.get("/kb/", response_model=list)
def list_kb(user=Depends(deps.get_current_user)):
    return routes.list_knowledge_bases(user)


@app.get("/documents/{document_id}/status")
def document_status(document_id: int, user=Depends(deps.get_current_user)):
    out = routes.get_document_status(user, document_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return out


@app.get("/kb/{kb_id}/members", response_model=list)
def list_kb_members(kb_id: int, user=Depends(deps.get_current_user)):
    return routes.list_kb_members(user, kb_id)


@app.post("/kb/{kb_id}/members")
def add_kb_member(kb_id: int, body: AddMemberRequest, user=Depends(deps.get_current_user)):
    return routes.add_kb_member(user, kb_id, body.email, body.role)


@app.patch("/kb/{kb_id}/members/{member_user_id}")
def update_kb_member_role(
    kb_id: int,
    member_user_id: int,
    body: UpdateMemberRoleRequest,
    user=Depends(deps.get_current_user),
):
    return routes.update_kb_member_role(user, kb_id, member_user_id, body.role)


@app.delete("/kb/{kb_id}/members/{member_user_id}")
def remove_kb_member(kb_id: int, member_user_id: int, user=Depends(deps.get_current_user)):
    return routes.remove_kb_member(user, kb_id, member_user_id)


@app.get("/chat/sessions", response_model=list)
def list_chat_sessions(kb_id: Optional[int] = Query(None), user=Depends(deps.get_current_user)):
    return routes.list_chat_sessions(user=user, kb_id=kb_id)


@app.get("/chat/sessions/{session_id}", response_model=dict)
def get_chat_session(session_id: str, limit: int = Query(100, ge=1, le=500), user=Depends(deps.get_current_user)):
    return routes.get_chat_session(user=user, session_id=session_id, limit=limit)


@app.delete("/chat/sessions/{session_id}", response_model=dict)
def delete_chat_session(session_id: str, user=Depends(deps.get_current_user)):
    return routes.delete_chat_session(user=user, session_id=session_id)
