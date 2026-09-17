from app.models.evidence import Evidence
from app.verification.conflict_detector import detect_conflicts


def _evidence(eid, domain, passage):
    return Evidence(evidence_id=eid, source_id=f"src-{eid}", url=f"https://{domain}/a", title="T", domain=domain, passage=passage)


def test_detects_numeric_conflict_between_different_domains():
    ev = [
        _evidence("E1", "a.com", "The company has 500 employees according to filings."),
        _evidence("E2", "b.com", "The company has 700 employees as of last year."),
    ]
    conflicts = detect_conflicts(ev)
    assert len(conflicts) >= 1
    assert conflicts[0].position_a_sources == ["E1"] or conflicts[0].position_b_sources == ["E1"]


def test_no_conflict_when_numbers_agree():
    ev = [
        _evidence("E1", "a.com", "The company has 500 employees."),
        _evidence("E2", "b.com", "The company has 500 employees."),
    ]
    conflicts = detect_conflicts(ev)
    assert conflicts == []


def test_same_domain_not_treated_as_independent_conflict():
    ev = [
        _evidence("E1", "a.com", "The company has 500 employees."),
        _evidence("E2", "a.com", "The company has 700 employees."),
    ]
    conflicts = detect_conflicts(ev)
    assert conflicts == []


def test_small_numeric_difference_not_flagged():
    ev = [
        _evidence("E1", "a.com", "Revenue grew 40 percent last quarter."),
        _evidence("E2", "b.com", "Revenue grew 40.1 percent last quarter."),
    ]
    conflicts = detect_conflicts(ev)
    assert conflicts == []


def test_employee_count_regression():
    # Regression: snippets from two independent domains disagreeing on the
    # employee count must be detected even when titles are near-identical.
    ev = [
        _evidence("E1", "a.com", "The company has 500 employees today."),
        _evidence("E2", "b.com", "The company has 700 employees today."),
    ]
    conflicts = detect_conflicts(ev)
    assert len(conflicts) >= 1
    assert conflicts[0].topic == "employees"


def test_dollars_and_thousands_conflict():
    ev = [
        _evidence("E1", "a.com", "The deal is worth $3 million."),
        _evidence("E2", "b.com", "The deal is worth $30 million."),
    ]
    conflicts = detect_conflicts(ev)
    assert len(conflicts) >= 1
