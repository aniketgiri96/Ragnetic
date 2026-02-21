from app.api import routes


def test_fallback_tech_stack_is_clean_and_extractive():
    question = "what is the tech stack aniket knows"
    sources = [
        {
            "snippet": (
                "Expert Copilot Dashboard | React, Material UI, Context API, WebSockets. "
                "Deep Search GenAI Content Retrieval System | Python, Supabase, SSE. "
                "Tools include Git, Jira, and CI/CD."
            )
        }
    ]
    out = routes._fallback_answer_from_sources(question, sources, "ReadTimeout")
    assert "LLM unavailable (ReadTimeout)" in out
    assert "React" in out
    assert "Material UI" in out
    assert "Python" in out
    assert "Supabase" in out
    assert "CI/CD" in out
    assert "Using top retrieved source instead" not in out


def test_fallback_general_question_returns_compact_bullets():
    question = "what does this profile mention"
    sources = [
        {"snippet": "Line one about product work.\nLine two about backend APIs."},
        {"snippet": "Line three about dashboards and telemetry."},
    ]
    out = routes._fallback_answer_from_sources(question, sources, "ReadTimeout")
    assert "LLM unavailable (ReadTimeout)" in out
    assert "Retrieved context:" in out
    assert "- Line one about product work. Line two about backend APIs." in out
