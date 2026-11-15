"""Small validators shared by several request schemas."""
import re

_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

NEEDS_WORDS_MESSAGE = "Write it in words: it needs at least one letter, not only numbers or symbols."


def require_letter(value: str) -> str:
    """Free-text reasons and descriptions must contain at least one letter,
    so "123123" or "???" is not accepted as an explanation."""
    value = value.strip()
    if not _LETTER.search(value):
        raise ValueError(NEEDS_WORDS_MESSAGE)
    return value
