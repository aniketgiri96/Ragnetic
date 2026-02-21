"""Knowledge-base scoped access control helpers."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.document import KnowledgeBase, KnowledgeBaseMembership, KnowledgeBaseRole
from app.models.user import User

ROLE_RANK = {
    KnowledgeBaseRole.VIEWER: 1,
    KnowledgeBaseRole.EDITOR: 2,
    KnowledgeBaseRole.OWNER: 3,
}


def _role_at_least(role: str, min_role: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 0)


def get_default_accessible_kb_id(db: Session, user_id: int, min_role: str = KnowledgeBaseRole.VIEWER) -> int | None:
    memberships = (
        db.query(KnowledgeBaseMembership)
        .filter(KnowledgeBaseMembership.user_id == user_id)
        .order_by(KnowledgeBaseMembership.created_at.asc())
        .all()
    )
    for m in memberships:
        if _role_at_least(m.role, min_role):
            return m.knowledge_base_id
    return None


def require_kb_access(db: Session, user_id: int, kb_id: int, min_role: str = KnowledgeBaseRole.VIEWER) -> KnowledgeBaseMembership:
    m = (
        db.query(KnowledgeBaseMembership)
        .filter(
            KnowledgeBaseMembership.user_id == user_id,
            KnowledgeBaseMembership.knowledge_base_id == kb_id,
        )
        .first()
    )
    if not m or not _role_at_least(m.role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for knowledge base {kb_id}",
        )
    return m


def list_user_knowledge_bases(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(KnowledgeBase, KnowledgeBaseMembership.role)
        .join(KnowledgeBaseMembership, KnowledgeBaseMembership.knowledge_base_id == KnowledgeBase.id)
        .filter(KnowledgeBaseMembership.user_id == user_id)
        .order_by(KnowledgeBase.created_at.asc())
        .all()
    )
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "role": role,
        }
        for kb, role in rows
    ]


def bootstrap_user_kb(db: Session, user: User) -> KnowledgeBase:
    """Create a personal KB and owner membership for a new user."""
    base_name = user.email.split("@", 1)[0].strip() or "User"
    kb_name = f"{base_name.title()} KB"
    suffix = 1
    existing_names = {name for (name,) in db.query(KnowledgeBase.name).all()}
    final_name = kb_name
    while final_name in existing_names:
        suffix += 1
        final_name = f"{kb_name} {suffix}"

    kb = KnowledgeBase(name=final_name, description=f"Personal knowledge base for {user.email}")
    db.add(kb)
    db.flush()
    db.add(
        KnowledgeBaseMembership(
            knowledge_base_id=kb.id,
            user_id=user.id,
            role=KnowledgeBaseRole.OWNER,
        )
    )
    return kb

