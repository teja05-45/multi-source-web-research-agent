from app.models.search import SearchResult
from app.processing.ranker import rank_results


def _result(title, snippet, domain, url="https://x.com/a"):
    canonical = url
    return SearchResult(
        result_id=SearchResult.make_id(canonical),
        providers=["duckduckgo"],
        title=title,
        url=url,
        canonical_url=canonical,
        domain=domain,
        snippet=snippet,
    )


def test_more_relevant_result_ranks_higher():
    query = "python asyncio event loop"
    relevant = _result("Python asyncio event loop guide", "Learn about asyncio event loop in python", "docs.python.org")
    irrelevant = _result("Best recipes for dinner", "cooking tips", "example.com")

    ranked = rank_results(query, [irrelevant, relevant])
    assert ranked[0] is relevant
    assert ranked[0].final_score > ranked[1].final_score


def test_official_docs_outrank_community_for_documentation_question():
    query = "official documentation for requests library syntax"
    docs = _result("Requests library documentation", "official docs for requests", "docs.python.org")
    forum = _result("Requests library documentation discussion", "forum discussion about requests", "stackoverflow.com")

    ranked = rank_results(query, [forum, docs])
    assert ranked[0].domain == "docs.python.org"


def test_community_source_not_penalized_for_experience_question():
    query = "developer experience opinions using rust for a side project"
    community = _result("My experience using rust", "developer opinions on rust side project", "reddit.com")
    unrelated_official = _result("Rust language reference", "official rust reference", "docs.python.org")

    ranked = rank_results(query, [unrelated_official, community])
    # Community source authority score should not be penalized to near-zero.
    community_result = next(r for r in ranked if r.domain == "reddit.com")
    assert community_result.authority_score >= 0.5


def test_scores_are_bounded_between_0_and_1():
    result = _result("Some Title", "some snippet text", "example.com")
    ranked = rank_results("some title snippet", [result])
    r = ranked[0]
    assert 0.0 <= r.relevance_score <= 1.0
    assert 0.0 <= r.authority_score <= 1.0
    assert 0.0 <= r.freshness_score <= 1.0
    assert 0.0 <= r.final_score <= 1.0
