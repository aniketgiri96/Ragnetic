"""Ragnetic FastAPI application."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from app.api import auth, deps, routes
from app.models.init_db import init_db


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
    file: UploadFile = File(...),
    kb_id: int = Query(None),
    user=Depends(deps.get_current_user),
):
    return await routes.upload_document(user=user, file=file, kb_id=kb_id)


@app.get("/search/")
async def search_documents(
    query: str,
    kb_id: int = Query(None),
    user=Depends(deps.get_current_user),
):
    return await routes.search_documents(user=user, query=query, kb_id=kb_id)


@app.post("/chat/")
async def chat_endpoint(
    body: ChatRequest,
    user=Depends(deps.get_current_user),
):
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
