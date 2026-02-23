"""Knowledge-base scoped access control helpers."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.document import KnowledgeBase, KnowledgeBaseMembership, KnowledgeBaseRole
from app.models.tenant import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    Team,
    TeamKnowledgeBaseAccess,
    TeamMembership,
    TeamRole,
)
from app.models.user import User

ROLE_RANK = {
    KnowledgeBaseRole.API_USER: 1,
    KnowledgeBaseRole.VIEWER: 1,
    KnowledgeBaseRole.EDITOR: 2,
    KnowledgeBaseRole.OWNER: 3,
}


@dataclass
class AccessGrant:
    knowledge_base_id: int
    user_id: int
    role: str
    source: str


def _role_at_least(role: str, min_role: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(min_role, 0)


def _max_role(roles: list[str]) -> str | None:
    if not roles:
        return None
    return max(roles, key=lambda role: ROLE_RANK.get(role, 0))


def _effective_kb_access(db: Session, user_id: int, kb_id: int) -> AccessGrant | None:
    direct_roles = [
        role
        for (role,) in (
            db.query(KnowledgeBaseMembership.role)
            .filter(
                KnowledgeBaseMembership.user_id == user_id,
                KnowledgeBaseMembership.knowledge_base_id == kb_id,
            )
            .all()
        )
    ]
    team_roles = [
        role
        for (role,) in (
            db.query(TeamKnowledgeBaseAccess.role)
            .join(TeamMembership, TeamMembership.team_id == TeamKnowledgeBaseAccess.team_id)
            .filter(
                TeamMembership.user_id == user_id,
                TeamKnowledgeBaseAccess.knowledge_base_id == kb_id,
            )
            .all()
        )
    ]

    best_direct = _max_role(direct_roles)
    best_team = _max_role(team_roles)
    if best_direct is None and best_team is None:
        return None
    if best_team is not None and (best_direct is None or ROLE_RANK.get(best_team, 0) > ROLE_RANK.get(best_direct, 0)):
        return AccessGrant(knowledge_base_id=kb_id, user_id=user_id, role=best_team, source="team")
    return AccessGrant(knowledge_base_id=kb_id, user_id=user_id, role=best_direct or best_team or "", source="direct")


def get_default_accessible_kb_id(db: Session, user_id: int, min_role: str = KnowledgeBaseRole.VIEWER) -> int | None:
    direct_ids = [
        kb_id
        for (kb_id,) in (
            db.query(KnowledgeBaseMembership.knowledge_base_id)
            .filter(KnowledgeBaseMembership.user_id == user_id)
            .all()
        )
    ]
    team_ids = [
        kb_id
        for (kb_id,) in (
            db.query(TeamKnowledgeBaseAccess.knowledge_base_id)
            .join(TeamMembership, TeamMembership.team_id == TeamKnowledgeBaseAccess.team_id)
            .filter(TeamMembership.user_id == user_id)
            .all()
        )
    ]
    for kb_id in sorted(set([*direct_ids, *team_ids])):
        grant = _effective_kb_access(db, user_id, kb_id)
        if grant and _role_at_least(grant.role, min_role):
            return kb_id
    return None


def require_kb_access(db: Session, user_id: int, kb_id: int, min_role: str = KnowledgeBaseRole.VIEWER) -> AccessGrant:
    grant = _effective_kb_access(db, user_id, kb_id)
    if not grant or not _role_at_least(grant.role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for knowledge base {kb_id}",
        )
    return grant


def list_user_knowledge_bases(db: Session, user_id: int) -> list[dict]:
    direct_rows = (
        db.query(KnowledgeBase, KnowledgeBaseMembership.role)
        .join(KnowledgeBaseMembership, KnowledgeBaseMembership.knowledge_base_id == KnowledgeBase.id)
        .filter(KnowledgeBaseMembership.user_id == user_id)
        .all()
    )
    team_rows = (
        db.query(KnowledgeBase, TeamKnowledgeBaseAccess.role)
        .join(TeamKnowledgeBaseAccess, TeamKnowledgeBaseAccess.knowledge_base_id == KnowledgeBase.id)
        .join(TeamMembership, TeamMembership.team_id == TeamKnowledgeBaseAccess.team_id)
        .filter(TeamMembership.user_id == user_id)
        .all()
    )
    kb_by_id: dict[int, dict] = {}
    for kb, role in [*direct_rows, *team_rows]:
        current = kb_by_id.get(kb.id)
        if current is None or ROLE_RANK.get(role, 0) > ROLE_RANK.get(current["role"], 0):
            kb_by_id[kb.id] = {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "role": role,
            }
    return sorted(kb_by_id.values(), key=lambda row: row["id"])


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
    existing_org_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.role == OrganizationRole.OWNER,
        )
        .first()
    )
    needs_org_membership = existing_org_membership is None
    if existing_org_membership is not None:
        existing_org = db.query(Organization).filter(Organization.id == existing_org_membership.organization_id).first()
    if existing_org_membership is None or existing_org is None:
        base_org_name = f"{base_name.title()} Org"
        org_name = base_org_name
        suffix = 1
        existing_names = {name for (name,) in db.query(Organization.name).all()}
        while org_name in existing_names:
            suffix += 1
            org_name = f"{base_org_name} {suffix}"
        existing_org = Organization(name=org_name, description=f"Workspace for {user.email}")
        db.add(existing_org)
        db.flush()
        needs_org_membership = True

    if needs_org_membership:
        db.add(
            OrganizationMembership(
                organization_id=existing_org.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
        )
    team_name = "Default Team"
    team = (
        db.query(Team)
        .filter(
            Team.organization_id == existing_org.id,
            Team.name == team_name,
        )
        .first()
    )
    if team is None:
        team = Team(organization_id=existing_org.id, name=team_name, description="Default team")
        db.add(team)
        db.flush()
    team_membership = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == user.id,
        )
        .first()
    )
    if team_membership is None:
        db.add(
            TeamMembership(
                team_id=team.id,
                user_id=user.id,
                role=TeamRole.MANAGER,
            )
        )
    team_access = (
        db.query(TeamKnowledgeBaseAccess)
        .filter(
            TeamKnowledgeBaseAccess.team_id == team.id,
            TeamKnowledgeBaseAccess.knowledge_base_id == kb.id,
        )
        .first()
    )
    if team_access is None:
        db.add(
            TeamKnowledgeBaseAccess(
                team_id=team.id,
                knowledge_base_id=kb.id,
                role=KnowledgeBaseRole.OWNER,
            )
        )
    return kb
