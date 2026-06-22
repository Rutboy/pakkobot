from pakko.llm.prompts import SYSTEM_PROMPT


def test_system_prompt_requires_answer_with_uncertainty_note() -> None:
    assert "дай лучший полезный ответ из доступных данных" in SYSTEM_PROMPT
    assert "давай наиболее вероятный ответ" in SYSTEM_PROMPT
    assert "с пометкой о низкой уверенности" in SYSTEM_PROMPT
    assert "если чего-то не знаешь, прямо говори об этом;" not in SYSTEM_PROMPT


def test_system_prompt_requires_confidence_marker() -> None:
    assert "[[pakko_confidence level=high source=reliable web_needed=no]]" in SYSTEM_PROMPT
    assert "допустимые level: high, medium, low" in SYSTEM_PROMPT
    assert "допустимые source: reliable, mixed, weak, none" in SYSTEM_PROMPT
    assert "допустимые web_needed: yes, no" in SYSTEM_PROMPT
    assert "не объясняй пользователю этот маркер" in SYSTEM_PROMPT
    assert "естественной фразой вроде" not in SYSTEM_PROMPT


def test_system_prompt_avoids_robotic_opening_labels() -> None:
    assert "не начинай ответ с клише" in SYSTEM_PROMPT
    assert "стремись к максимальной уверенности" in SYSTEM_PROMPT
    assert "Пакко честно:" in SYSTEM_PROMPT
    assert "Коротко:" in SYSTEM_PROMPT
    assert "если отвечаешь по-русски, называй себя" not in SYSTEM_PROMPT


def test_system_prompt_prioritizes_current_sources_for_news() -> None:
    assert "ориентируйся на текущую дату UTC" in SYSTEM_PROMPT
    assert "с датой публикации или обновления максимально близкой к ней" in SYSTEM_PROMPT
    assert "для новостей" in SYSTEM_PROMPT
    assert "сначала ищи материалы за сегодня" in SYSTEM_PROMPT
    assert "явно называй их даты" in SYSTEM_PROMPT
