"""The meal periods a dish can be served in, stored on the dish as text."""

ALL = ("Breakfast", "Lunch", "Dinner")
DEFAULT = ("Lunch", "Dinner")


def to_text(periods) -> str:
    """["Dinner", "Lunch"] -> "Lunch,Dinner" (always in day order, no duplicates)."""
    wanted = set(periods)
    return ",".join(p for p in ALL if p in wanted)


def from_text(text: str | None) -> list[str]:
    if not text:
        return list(DEFAULT)
    return [p for p in text.split(",") if p in ALL]


def serves(text: str | None, period: str | None) -> bool:
    """Whether a dish whose periods are [text] is served in [period]. No period
    (or an unknown dish) is never a reason to refuse."""
    return period is None or period in from_text(text)
