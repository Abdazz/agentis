"""Language resolution helpers (Feature LANG-1, BR-LANG-01/03).

Supported languages are fixed to en/fr across the whole product (i18n
messages, system prompt LANGUAGE_INSTRUCTION dict, this detector) — see
spec §11.1.
"""
import structlog

log = structlog.get_logger()

SUPPORTED_LANGUAGES = ("en", "fr")

_detector = None


def _get_detector():
    # Lazy-loaded: lingua's language models are ~170MB and take a moment
    # to build. Loading at import time would slow every cold start of
    # every process that imports this module, most of which never call
    # detect_language_from_text() at all.
    global _detector
    if _detector is None:
        from lingua import Language, LanguageDetectorBuilder
        _detector = LanguageDetectorBuilder.from_languages(
            Language.ENGLISH, Language.FRENCH
        ).build()
    return _detector


def match_accept_language(header: str | None) -> str | None:
    """Parse an Accept-Language header (RFC 9110, e.g.
    'fr-CA,fr;q=0.9,en;q=0.8') and return 'en' or 'fr' if one of the
    offered tags matches a supported language, else None. Entries are
    already sent by browsers in descending preference order, so the
    first match wins."""
    if not header:
        return None
    for part in header.split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag:
            continue
        primary = tag.split("-")[0]
        if primary in SUPPORTED_LANGUAGES:
            return primary
    return None


def detect_language_from_text(text: str, confidence_threshold: float = 0.8) -> str | None:
    """Detect en/fr from free text via lingua. Returns None if the text
    is empty or the top match's confidence is below the threshold
    (BR-LANG-03: "if detection confidence < 0.8, default to the user's
    account language" — the caller supplies that fallback)."""
    if not text or not text.strip():
        return None
    try:
        detector = _get_detector()
        confidences = detector.compute_language_confidence_values(text)
    except Exception as e:
        log.warning("language_detection_failed", error=str(e))
        return None
    if not confidences:
        return None
    top = confidences[0]
    if top.value < confidence_threshold:
        return None
    from lingua import Language
    if top.language == Language.ENGLISH:
        return "en"
    if top.language == Language.FRENCH:
        return "fr"
    return None
