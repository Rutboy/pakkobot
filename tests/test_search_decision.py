from pakko.search import needs_web_search


def test_needs_web_search_for_current_data() -> None:
    assert needs_web_search("найди свежую статистику рынка игр")
    assert needs_web_search("What are the latest AI news today?")


def test_does_not_search_for_general_knowledge() -> None:
    assert not needs_web_search("объясни, что такое бинарный поиск")
