from pakko.assistant.confidence import assess_confidence


def test_assess_confidence_parses_and_strips_marker() -> None:
    assessment = assess_confidence(
        "Ответ для пользователя.\n[[pakko_confidence level=medium source=reliable web_needed=no]]"
    )

    assert assessment.clean_text == "Ответ для пользователя."
    assert assessment.level == "medium"
    assert assessment.source == "reliable"
    assert assessment.web_needed == "no"
    assert assessment.marker_found
    assert not assessment.should_improve_with_web_search


def test_assess_confidence_defaults_missing_marker_to_needs_improvement() -> None:
    assessment = assess_confidence("Ответ без технического маркера.")

    assert assessment.clean_text == "Ответ без технического маркера."
    assert assessment.level == "low"
    assert assessment.source == "none"
    assert assessment.web_needed == "yes"
    assert not assessment.marker_found
    assert assessment.should_improve_with_web_search


def test_assess_confidence_low_or_web_needed_requires_improvement() -> None:
    low = assess_confidence("X [[pakko_confidence level=low source=weak web_needed=no]]")
    medium_needs_web = assess_confidence(
        "X [[pakko_confidence level=medium source=mixed web_needed=yes]]"
    )

    assert low.should_improve_with_web_search
    assert medium_needs_web.should_improve_with_web_search
