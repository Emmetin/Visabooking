"""Browser steps: open the dashboard, start a booking, pick the dropdowns, read the result.

Login, captcha and the final booking confirmation are always left to the user.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from .config import Config
from .parsing import PageState, SlotStatus, classify_page, classify_slots, slot_snippet

log = logging.getLogger(__name__)

NEW_BOOKING_RE = re.compile(
    r"start new booking|book (an )?appointment|записаться|новая запись|начать.*запис|забронировать",
    re.IGNORECASE,
)


class OptionNotFound(Exception):
    def __init__(self, index: int, wanted: str, available: list[str]):
        self.index, self.wanted, self.available = index, wanted, available
        super().__init__(f"dropdown #{index + 1}: no option matches {wanted!r}")


@dataclass
class CheckResult:
    state: PageState
    slots: SlotStatus = SlotStatus.UNKNOWN
    snippet: str = ""
    screenshot: Path | None = None


def body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=10_000)
    except PWTimeout:
        return ""


def current_state(page: Page) -> PageState:
    return classify_page(page.url, body_text(page))


def settle(page: Page, timeout_ms: int = 15_000) -> None:
    # VFS keeps analytics connections open, so networkidle may never come; that's fine.
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PWTimeout:
        pass


def screenshot(page: Page, folder: Path, tag: str) -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{tag}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def wait_for_user(page: Page, timeout_s: float = 15 * 60, poll_s: float = 5) -> bool:
    """Wait while the user logs in or solves a check in the open window."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        page.wait_for_timeout(poll_s * 1000)
        if current_state(page) is PageState.OK:
            return True
    return False


def start_new_booking(page: Page) -> None:
    button = page.get_by_role("button", name=NEW_BOOKING_RE)
    if button.count() == 0:
        button = page.get_by_text(NEW_BOOKING_RE)
    button.first.click(timeout=30_000)
    settle(page)


def select_option(page: Page, index: int, pattern: str) -> str:
    dropdown = page.locator("mat-select").nth(index)
    dropdown.wait_for(state="visible", timeout=30_000)
    dropdown.click()
    options = page.locator("mat-option")
    options.first.wait_for(state="visible", timeout=15_000)
    texts = [t.strip() for t in options.all_inner_texts()]
    for i, text in enumerate(texts):
        if re.search(pattern, text, re.IGNORECASE):
            options.nth(i).click()
            settle(page, 10_000)
            return text
    page.keyboard.press("Escape")
    raise OptionNotFound(index, pattern, texts)


def wait_for_slot_message(page: Page, timeout_s: float = 30) -> str:
    deadline = time.monotonic() + timeout_s
    text = body_text(page)
    while classify_slots(text) is SlotStatus.UNKNOWN and time.monotonic() < deadline:
        page.wait_for_timeout(1000)
        text = body_text(page)
    return text


def check_once(page: Page, cfg: Config) -> CheckResult:
    page.goto(cfg.dashboard_url, wait_until="domcontentloaded", timeout=60_000)
    settle(page)
    state = current_state(page)
    if state is not PageState.OK:
        return CheckResult(state)

    start_new_booking(page)
    for i, pattern in enumerate(cfg.selections):
        chosen = select_option(page, i, pattern)
        log.info("Список %d: выбрано «%s»", i + 1, chosen)

    text = wait_for_slot_message(page)
    state = classify_page(page.url, text)
    if state is not PageState.OK:
        return CheckResult(state)

    slots = classify_slots(text)
    shot = None if slots is SlotStatus.NONE else screenshot(page, cfg.screenshots_dir, slots.value)
    return CheckResult(state, slots, slot_snippet(text), shot)
