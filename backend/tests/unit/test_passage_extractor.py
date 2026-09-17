from app.retrieval.passage_extractor import extract_relevant_passages


def test_returns_query_relevant_sentences_over_leading_text():
    text = (
        "Welcome to our website. Navigation links go here. "
        "The company has exactly 500 employees as of last quarter. "
        "We sell widgets in forty countries. "
        "Employee headcount is a key metric for investors."
    )
    passage = extract_relevant_passages(text, "How many employees does the company have?", max_chars=300)
    assert "500 employees" in passage
    assert "Navigation links" not in passage


def test_fallback_to_leading_text_when_no_overlap():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    passage = extract_relevant_passages(text, "completely unrelated query words here", max_chars=100)
    assert passage == text[:100]


def test_empty_input_returns_empty():
    assert extract_relevant_passages("", "query") == ""


def test_preserves_original_order():
    text = "Sentence with employees here. First sentence about other stuff. Another employees mention."
    passage = extract_relevant_passages(text, "employees", max_chars=500)
    assert passage.index("Sentence with employees") < passage.index("Another employees")