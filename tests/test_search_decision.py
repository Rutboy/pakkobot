from pakko.search import needs_web_search


def test_needs_web_search_for_current_data() -> None:
    assert needs_web_search("найди свежую статистику рынка игр")
    assert needs_web_search("What are the latest AI news today?")


def test_does_not_search_for_general_knowledge() -> None:
    assert not needs_web_search("объясни, что такое бинарный поиск")


def test_needs_web_search_for_game_release_dates() -> None:
    assert needs_web_search(
        "собери список анонсированных релизов с известной датой, которые выйдут на PC"
    )
    assert needs_web_search("какие игры с датой выхода в сентябре 2026")


def test_needs_web_search_for_now_price_and_official_queries() -> None:
    assert needs_web_search("кто сейчас CEO OpenAI")
    assert needs_web_search("сколько стоит ChatGPT Plus на данный момент")
    assert needs_web_search("проверь официальную дату релиза")
    assert needs_web_search("What is the current official price?")
