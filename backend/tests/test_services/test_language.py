import pytest
from app.services.language import match_accept_language, detect_language_from_text


# --- match_accept_language (BR-LANG-01) ---

def test_match_accept_language_none_returns_none():
    assert match_accept_language(None) is None


def test_match_accept_language_empty_returns_none():
    assert match_accept_language("") is None


def test_match_accept_language_simple_match():
    assert match_accept_language("fr") == "fr"


def test_match_accept_language_with_region_subtag():
    assert match_accept_language("fr-CA") == "fr"


def test_match_accept_language_picks_first_supported_in_preference_order():
    assert match_accept_language("de-DE,fr;q=0.9,en;q=0.8") == "fr"


def test_match_accept_language_no_supported_tag_returns_none():
    assert match_accept_language("de-DE,es;q=0.9") is None


def test_match_accept_language_case_insensitive():
    assert match_accept_language("EN-US") == "en"


# --- detect_language_from_text (BR-LANG-03) ---

def test_detect_language_empty_text_returns_none():
    assert detect_language_from_text("") is None
    assert detect_language_from_text("   ") is None


def test_detect_language_french_text():
    assert detect_language_from_text(
        "Peux-tu rechercher les derniers articles sur l'intelligence artificielle "
        "et me faire un résumé détaillé en français ?"
    ) == "fr"


def test_detect_language_english_text():
    assert detect_language_from_text(
        "Please research the latest articles about artificial intelligence "
        "and give me a detailed summary."
    ) == "en"


def test_detect_language_below_confidence_threshold_returns_none():
    # A single ambiguous word shared across many languages should not
    # confidently resolve to either supported language.
    result = detect_language_from_text("ok", confidence_threshold=0.999999)
    assert result is None
