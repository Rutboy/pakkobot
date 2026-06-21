def needs_web_search(text: str) -> bool:
    """Pakko is search-first: every non-empty user request should use web search."""
    return bool(text.strip())
