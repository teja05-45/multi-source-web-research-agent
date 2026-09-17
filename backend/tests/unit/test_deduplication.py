from app.models.search import RawSearchResult
from app.processing.deduplicator import deduplicate_results
from app.processing.normalizer import normalize_results


def test_exact_url_duplicates_merged_with_tracking_params():
    raw = [
        RawSearchResult(provider="duckduckgo", title="Article Title", url="https://example.com/article", snippet="a"),
        RawSearchResult(
            provider="tavily",
            title="Article Title",
            url="https://example.com/article?utm_source=google",
            snippet="b",
        ),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 1
    assert removed == 1
    assert set(deduped[0].providers) == {"duckduckgo", "tavily"}
    assert deduped[0].duplicate_count == 1


def test_near_identical_titles_flagged_as_duplicate():
    raw = [
        RawSearchResult(provider="duckduckgo", title="Company X Raises $50 Million In Funding", url="https://a.com/x"),
        RawSearchResult(provider="tavily", title="Company X Raises $50 Million in Funding", url="https://b.com/y"),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 1
    assert removed == 1


def test_distinct_results_are_not_merged():
    raw = [
        RawSearchResult(provider="duckduckgo", title="Python Tutorial for Beginners", url="https://a.com/py"),
        RawSearchResult(provider="tavily", title="JavaScript Tutorial for Beginners", url="https://b.com/js"),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 2
    assert removed == 0


def test_similar_template_titles_from_different_sources_are_not_merged():
    # "Employee count A" vs "Employee count B" score ~0.93 — two genuinely
    # different articles. Merging them would hide a numeric conflict between
    # independent sources, so they must stay separate.
    raw = [
        RawSearchResult(provider="duckduckgo", title="Employee count A", url="https://a.com/x", snippet="The company has 500 employees today."),
        RawSearchResult(provider="tavily", title="Employee count B", url="https://b.com/y", snippet="The company has 700 employees today."),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 2
    assert removed == 0


def test_identical_titles_with_conflicting_snippets_are_not_merged():
    # Exact title match normally means a wire reprint — but here the two
    # sources disagree numerically, so folding would hide a conflict.
    raw = [
        RawSearchResult(provider="duckduckgo", title="Employee count", url="https://a.com/x", snippet="The company has 500 employees today."),
        RawSearchResult(provider="tavily", title="Employee count", url="https://b.com/y", snippet="The company has 700 employees today."),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 2
    assert removed == 0


def test_identical_titles_with_agreeing_snippets_are_merged():
    raw = [
        RawSearchResult(provider="duckduckgo", title="Company announcement", url="https://a.com/x", snippet="The company announced a new product today."),
        RawSearchResult(provider="tavily", title="Company announcement", url="https://b.com/y", snippet="The company announced a new product today."),
    ]
    normalized = normalize_results(raw)
    deduped, removed = deduplicate_results(normalized)

    assert len(deduped) == 1
    assert removed == 1
