from pakko.search import needs_web_search


def test_needs_web_search_for_any_non_empty_request() -> None:
    assert needs_web_search("explain what binary search is")
    assert needs_web_search("What are the latest AI news today?")
    assert needs_web_search("  find fresh sources  ")


def test_does_not_search_for_empty_request() -> None:
    assert not needs_web_search("")
    assert not needs_web_search("   ")
