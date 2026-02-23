from app.services.citations import append_citation_legend


def test_append_citation_legend_groups_duplicate_files():
    answer = "Summary.\n\nCitations: [Source 1], [Source 2], [Source 3]"
    sources = [
        {"metadata": {"source": "gridbase_prd.docx"}},
        {"metadata": {"source": "gridbase_prd.docx"}},
        {"metadata": {"source": "gridbase_prd.docx"}},
    ]
    out = append_citation_legend(answer, sources)
    assert "Source references:" in out
    assert "[Source 1, 2, 3] gridbase_prd.docx" in out
    assert out.count("gridbase_prd.docx") == 1


def test_append_citation_legend_groups_by_source_name():
    answer = "Summary.\n\nCitations: [Source 1], [Source 2], [Source 3]"
    sources = [
        {"metadata": {"source": "a.docx"}},
        {"metadata": {"source": "b.docx"}},
        {"metadata": {"source": "a.docx"}},
    ]
    out = append_citation_legend(answer, sources)
    assert "[Source 1, 3] a.docx" in out
    assert "[Source 2] b.docx" in out


def test_append_citation_legend_skips_when_no_citations():
    answer = "No citation markers."
    sources = [{"metadata": {"source": "a.docx"}}]
    assert append_citation_legend(answer, sources) == answer
