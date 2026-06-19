from pakko.llm.prompts import SYSTEM_PROMPT


def test_system_prompt_requires_answer_with_uncertainty_note() -> None:
    assert "дай лучший полезный ответ из доступных данных" in SYSTEM_PROMPT
    assert "давай наиболее вероятный ответ" in SYSTEM_PROMPT
    assert "с пометкой о низкой уверенности" in SYSTEM_PROMPT
    assert "если уверенность низкая" in SYSTEM_PROMPT.lower()
    assert "не до конца уверен" in SYSTEM_PROMPT
    assert "если чего-то не знаешь, прямо говори об этом;" not in SYSTEM_PROMPT


def test_system_prompt_avoids_robotic_opening_labels() -> None:
    assert "не начинай ответ с клише" in SYSTEM_PROMPT
    assert "стремись к максимальной уверенности" in SYSTEM_PROMPT
    assert "Пакко честно:" in SYSTEM_PROMPT
    assert "Коротко:" in SYSTEM_PROMPT
    assert "если отвечаешь по-русски, называй себя" not in SYSTEM_PROMPT
