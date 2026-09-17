from app.models.claims import Claim, SupportStatus
from app.models.evidence import Evidence
from app.verification.citation_validator import validate_claims


def _evidence(eid, passage):
    return Evidence(evidence_id=eid, source_id=f"s-{eid}", url="https://a.com", title="T", domain="a.com", passage=passage)


def test_claim_with_no_citations_is_insufficient_evidence():
    claims = [Claim(claim_id="c1", text="Revenue increased by 40 percent.", citation_evidence_ids=[])]
    verified, removed = validate_claims(claims, {}, [])
    assert verified[0].support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert removed == 1


def test_claim_citing_nonexistent_evidence_id_is_flagged():
    claims = [Claim(claim_id="c1", text="Revenue increased by 40 percent.", citation_evidence_ids=["E99"])]
    evidence_by_id = {"E1": _evidence("E1", "Some unrelated passage about weather.")}
    verified, removed = validate_claims(claims, evidence_by_id, [])
    assert verified[0].support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert removed == 1


def test_claim_with_low_lexical_overlap_is_flagged():
    evidence_by_id = {"E1": _evidence("E1", "The weather today is sunny and warm.")}
    claims = [Claim(claim_id="c1", text="Revenue increased by 40 percent this quarter.", citation_evidence_ids=["E1"])]
    verified, removed = validate_claims(claims, evidence_by_id, [])
    assert verified[0].support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert removed == 1


def test_claim_with_good_overlap_is_supported():
    evidence_by_id = {"E1": _evidence("E1", "Company revenue increased by 40 percent this quarter according to filings.")}
    claims = [Claim(claim_id="c1", text="Revenue increased by 40 percent this quarter.", citation_evidence_ids=["E1"])]
    verified, removed = validate_claims(claims, evidence_by_id, [])
    assert verified[0].support_status == SupportStatus.SUPPORTED
    assert removed == 0


def test_claim_citing_conflicted_evidence_is_contradicted():
    from app.models.claims import Conflict

    evidence_by_id = {"E1": _evidence("E1", "The company has 500 employees according to reports.")}
    conflicts = [
        Conflict(topic="employees", position_a="500 employees", position_a_sources=["E1"], position_b="700 employees", position_b_sources=["E2"])
    ]
    claims = [Claim(claim_id="c1", text="The company has 500 employees according to reports.", citation_evidence_ids=["E1"])]
    verified, removed = validate_claims(claims, evidence_by_id, conflicts)
    assert verified[0].support_status == SupportStatus.CONTRADICTED
