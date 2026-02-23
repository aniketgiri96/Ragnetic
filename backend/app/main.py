"""Ragnetic FastAPI application."""
from contextlib import asynccontextmanager
from datetime import datetime
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
    async_mode: Optional[bool] = None


class ChatFeedbackRequest(BaseModel):
    message_id: int
    rating: str
    comment: Optional[str] = None


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"


class AddOrganizationMemberRequest(BaseModel):
    email: EmailStr
    role: str = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class CreateOrganizationRequest(BaseModel):
    name: str
    description: Optional[str] = None


class CreateTeamRequest(BaseModel):
    name: str
    description: Optional[str] = None


class AddTeamMemberRequest(BaseModel):
    email: EmailStr
    role: str = "member"


class AssignTeamKbAccessRequest(BaseModel):
    role: str = "viewer"


class RenameDocumentRequest(BaseModel):
    filename: str


class CreateKnowledgeBaseRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateKnowledgeBaseRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ConnectorSyncStateRequest(BaseModel):
    source_type: str
    scope_key: str
    cursor: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    successful: bool = True
    error: Optional[str] = None


class EmbeddingMigrationRequest(BaseModel):
    target_version: str


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
    replace_existing: bool = Query(True),
    user=Depends(deps.get_current_user),
):
    ip = request.client.host if request and request.client else "unknown"
    enforce_rate_limit("upload", key=f"user:{user.id}:ip:{ip}")
    return await routes.upload_document(user=user, file=file, kb_id=kb_id, replace_existing=replace_existing)


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
        async_mode=body.async_mode,
    )


@app.post("/chat/feedback", response_model=dict)
def submit_chat_feedback(
    body: ChatFeedbackRequest,
    user=Depends(deps.get_current_user),
):
    return routes.submit_chat_feedback(
        user=user,
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
    )


@app.post("/chat/stream")
async def chat_stream_endpoint(
    body: ChatRequest,
    request: Request,
    user=Depends(deps.get_current_user),
):
    ip = request.client.host if request and request.client else "unknown"
    enforce_rate_limit("chat", key=f"user:{user.id}:ip:{ip}")
    return await routes.chat_rag_stream(
        user=user,
        message=body.message,
        kb_id=body.kb_id,
        session_id=body.session_id,
    )


@app.get("/kb/", response_model=list)
def list_kb(user=Depends(deps.get_current_user)):
    return routes.list_knowledge_bases(user)


@app.get("/onboarding/status", response_model=dict)
def onboarding_status(user=Depends(deps.get_current_user)):
    return routes.get_onboarding_status(user)


@app.post("/onboarding/sample-kb", response_model=dict)
def onboarding_create_sample_kb(user=Depends(deps.get_current_user)):
    return routes.create_onboarding_sample_kb(user)


@app.get("/orgs/", response_model=list)
def list_orgs(user=Depends(deps.get_current_user)):
    return routes.list_organizations(user)


@app.post("/orgs/", response_model=dict)
def create_org(body: CreateOrganizationRequest, user=Depends(deps.get_current_user)):
    return routes.create_organization(user=user, name=body.name, description=body.description)


@app.post("/orgs/{org_id}/members", response_model=dict)
def add_org_member(org_id: int, body: AddOrganizationMemberRequest, user=Depends(deps.get_current_user)):
    return routes.add_organization_member(
        user=user,
        org_id=org_id,
        email=body.email,
        role=body.role,
    )


@app.get("/orgs/{org_id}/teams", response_model=list)
def list_org_teams(org_id: int, user=Depends(deps.get_current_user)):
    return routes.list_organization_teams(user=user, org_id=org_id)


@app.post("/orgs/{org_id}/teams", response_model=dict)
def create_org_team(org_id: int, body: CreateTeamRequest, user=Depends(deps.get_current_user)):
    return routes.create_organization_team(
        user=user,
        org_id=org_id,
        name=body.name,
        description=body.description,
    )


@app.post("/teams/{team_id}/members", response_model=dict)
def add_team_member(team_id: int, body: AddTeamMemberRequest, user=Depends(deps.get_current_user)):
    return routes.add_team_member(
        user=user,
        team_id=team_id,
        email=body.email,
        role=body.role,
    )


@app.post("/teams/{team_id}/knowledge-bases/{kb_id}", response_model=dict)
def assign_team_kb(team_id: int, kb_id: int, body: AssignTeamKbAccessRequest, user=Depends(deps.get_current_user)):
    return routes.assign_team_kb_access(
        user=user,
        team_id=team_id,
        kb_id=kb_id,
        role=body.role,
    )


@app.get("/kb/{kb_id}/teams", response_model=list)
def list_kb_teams(kb_id: int, user=Depends(deps.get_current_user)):
    return routes.list_kb_team_access(user=user, kb_id=kb_id)


@app.get("/kb/{kb_id}/embeddings", response_model=dict)
def get_kb_embedding_registry(kb_id: int, user=Depends(deps.get_current_user)):
    return routes.get_embedding_registry(user=user, kb_id=kb_id)


@app.get("/kb/{kb_id}/analytics", response_model=dict)
def get_kb_analytics(
    kb_id: int,
    days: Optional[int] = Query(None, ge=1, le=90),
    user=Depends(deps.get_current_user),
):
    return routes.get_kb_rag_analytics(user=user, kb_id=kb_id, days=days)


@app.post("/kb/{kb_id}/embeddings/migrate", response_model=dict)
def start_kb_embedding_migration(
    kb_id: int,
    body: EmbeddingMigrationRequest,
    user=Depends(deps.get_current_user),
):
    return routes.start_embedding_migration_for_kb(
        user=user,
        kb_id=kb_id,
        target_version=body.target_version,
    )


@app.post("/kb/", response_model=dict)
def create_kb(body: CreateKnowledgeBaseRequest, user=Depends(deps.get_current_user)):
    return routes.create_knowledge_base(user=user, name=body.name, description=body.description)


@app.patch("/kb/{kb_id}", response_model=dict)
def update_kb(kb_id: int, body: UpdateKnowledgeBaseRequest, user=Depends(deps.get_current_user)):
    return routes.update_knowledge_base(
        user=user,
        kb_id=kb_id,
        name=body.name,
        description=body.description,
    )


@app.delete("/kb/{kb_id}", response_model=dict)
def delete_kb(kb_id: int, user=Depends(deps.get_current_user)):
    return routes.delete_knowledge_base(user=user, kb_id=kb_id)


@app.get("/kb/{kb_id}/audit", response_model=list)
def get_audit_logs(
    kb_id: int,
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = Query(None),
    user=Depends(deps.get_current_user),
):
    return routes.list_audit_logs(user=user, kb_id=kb_id, limit=limit, action=action)


@app.get("/documents/{document_id}/status")
def document_status(document_id: int, user=Depends(deps.get_current_user)):
    out = routes.get_document_status(user, document_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return out


@app.get("/documents", response_model=list)
def list_documents(kb_id: Optional[int] = Query(None), user=Depends(deps.get_current_user)):
    return routes.list_documents(user=user, kb_id=kb_id)


@app.get("/kb/{kb_id}/ingestion/dead-letter", response_model=list)
def list_ingestion_dead_letters(
    kb_id: int,
    limit: int = Query(100, ge=1, le=500),
    resolved: bool = Query(False),
    user=Depends(deps.get_current_user),
):
    return routes.list_ingestion_dead_letters(user=user, kb_id=kb_id, limit=limit, resolved=resolved)


@app.post("/ingestion/dead-letter/{dead_letter_id}/retry", response_model=dict)
def retry_ingestion_dead_letter(dead_letter_id: int, user=Depends(deps.get_current_user)):
    return routes.retry_ingestion_dead_letter(user=user, dead_letter_id=dead_letter_id)


@app.get("/kb/{kb_id}/connectors/sync-state", response_model=dict)
def get_connector_sync_state(
    kb_id: int,
    source_type: str = Query(...),
    scope_key: str = Query(...),
    user=Depends(deps.get_current_user),
):
    return routes.get_connector_sync_cursor(
        user=user,
        kb_id=kb_id,
        source_type=source_type,
        scope_key=scope_key,
    )


@app.post("/kb/{kb_id}/connectors/sync-state", response_model=dict)
def upsert_connector_sync_state(
    kb_id: int,
    body: ConnectorSyncStateRequest,
    user=Depends(deps.get_current_user),
):
    return routes.upsert_connector_sync_cursor(
        user=user,
        kb_id=kb_id,
        source_type=body.source_type,
        scope_key=body.scope_key,
        cursor=body.cursor,
        last_synced_at=body.last_synced_at,
        successful=body.successful,
        error=body.error,
    )


@app.patch("/documents/{document_id}", response_model=dict)
def rename_document(document_id: int, body: RenameDocumentRequest, user=Depends(deps.get_current_user)):
    return routes.rename_document(user=user, document_id=document_id, filename=body.filename)


@app.post("/documents/{document_id}/retry", response_model=dict)
def retry_document_ingestion(document_id: int, user=Depends(deps.get_current_user)):
    return routes.retry_document_ingestion(user=user, document_id=document_id)


@app.delete("/documents/{document_id}", response_model=dict)
def delete_document(document_id: int, user=Depends(deps.get_current_user)):
    return routes.delete_document(user=user, document_id=document_id)


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


@app.get("/chat/jobs/{job_id}", response_model=dict)
def get_chat_job(job_id: str, user=Depends(deps.get_current_user)):
    return routes.get_chat_job(user=user, job_id=job_id)
