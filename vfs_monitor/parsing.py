"""Pure text classification of VFS pages — no browser here, so it is easy to test."""

import re
from enum import Enum


class SlotStatus(Enum):
    AVAILABLE = "available"
    NONE = "none"
    UNKNOWN = "unknown"


class PageState(Enum):
    OK = "ok"
    LOGIN = "login"          # session expired, the user must log in
    CHALLENGE = "challenge"  # Cloudflare / "are you human" check, the user must solve it
    BLOCKED = "blocked"      # rate limited or temporarily banned, back off


# "No slots" is checked first: "нет доступных слотов" also contains "доступных слот".
_NO_SLOTS = [
    r"no appointment slots",
    r"no slots? (are |is )?(currently )?available",
    r"currently no (available )?(appointment|slot)",
    r"нет (доступных|свободных)",
    r"(доступных|свободных) (слотов|дат|мест|окон)[^.\n]{0,30}нет",
    r"отсутствуют",
]
_AVAILABLE = [
    r"earliest available (slot|appointment|date)",
    r"available slots? (for|on|from)",
    r"ближайш\w* (доступн|свободн)",
    r"(доступн|свободн)\w* (слот|дат|окн|запис)\w*[^.\n]{0,40}\d{1,2}[./-]\d{1,2}",
]
_CHALLENGE = [
    r"just a moment",
    r"verify you are human",
    r"checking your browser",
    r"подтвердите, что вы (человек|не робот)",
    r"проверка браузера",
]
_BLOCKED = [
    r"access denied",
    r"too many requests",
    r"error\s*(code)?\s*:?\s*(403|429|1015)",
    r"temporarily blocked",
    r"временно заблокирован",
    r"превышено количество",
]


def _search(patterns: list[str], text: str) -> re.Match | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match
    return None


def classify_page(url: str, text: str) -> PageState:
    if _search(_BLOCKED, text):
        return PageState.BLOCKED
    if _search(_CHALLENGE, text):
        return PageState.CHALLENGE
    if "/login" in url.lower():
        return PageState.LOGIN
    return PageState.OK


def classify_slots(text: str) -> SlotStatus:
    if _search(_NO_SLOTS, text):
        return SlotStatus.NONE
    if _search(_AVAILABLE, text):
        return SlotStatus.AVAILABLE
    return SlotStatus.UNKNOWN


def slot_snippet(text: str) -> str:
    """The line of the page that mentions slots, for the notification."""
    match = _search(_AVAILABLE, text) or _search(_NO_SLOTS, text)
    if not match:
        return ""
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return text[start: end if end != -1 else len(text)].strip()[:500]
