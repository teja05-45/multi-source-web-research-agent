from app.models.search import RawSearchResult
from app.processing.normalizer import normalize_results


def test_normalize_drops_results_missing_title_or_url():
    raw = [
        RawSearchResult(provider="duckduckgo", title="", url="https://a.com"),
        RawSearchResult(provider="duckduckgo", title="Valid", url=""),
        RawSearchResult(provider="duckduckgo", title="Valid Title", url="https://a.com/page"),
    ]
    normalized = normalize_results(raw)
    assert len(normalized) == 1
    assert normalized[0].title == "Valid Title"


def test_normalize_preserves_provenance():
    raw = [RawSearchResult(provider="tavily", title="T", url="https://a.com/page", snippet="s")]
    normalized = normalize_results(raw)
    assert normalized[0].providers == ["tavily"]
    assert normalized[0].domain == "a.com"
    assert normalized[0].snippet == "s"


def test_normalize_generates_stable_result_id_for_same_canonical_url():
    raw1 = [RawSearchResult(provider="duckduckgo", title="T", url="https://a.com/page")]
    raw2 = [RawSearchResult(provider="tavily", title="T", url="https://a.com/page?utm_source=x")]
    r1 = normalize_results(raw1)[0]
    r2 = normalize_results(raw2)[0]
    assert r1.result_id == r2.result_id
