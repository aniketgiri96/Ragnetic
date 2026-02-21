"""Create tables and default knowledge base."""
from app.models.base import Base, engine, SessionLocal
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, KnowledgeBase, KnowledgeBaseMembership
from app.models.user import User  # noqa: F401 - register model for create_all


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            if db.query(KnowledgeBase).first() is None:
                db.add(KnowledgeBase(name="Default", description="Default knowledge base"))
                db.commit()
        finally:
            db.close()
    except Exception:
        pass  # DB may be unavailable at startup (e.g. Docker not up yet)
