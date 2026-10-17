import logging
import platform
import subprocess
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._last_sent: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _api(self, method: str, **kwargs) -> None:
        if not self.enabled:
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/{method}", timeout=30, **kwargs
            )
            if not resp.ok:
                log.warning("Telegram %s failed: %s %s", method, resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            log.warning("Telegram %s failed: %s", method, e)

    def send(self, text: str, photo: Path | None = None) -> None:
        log.info("Уведомление: %s", text.replace("\n", " | "))
        if photo and photo.exists():
            with photo.open("rb") as f:
                self._api(
                    "sendPhoto",
                    data={"chat_id": self.chat_id, "caption": text[:1000]},
                    files={"photo": f},
                )
        else:
            self._api("sendMessage", data={"chat_id": self.chat_id, "text": text})

    def send_throttled(self, key: str, text: str, cooldown_s: float, photo: Path | None = None) -> None:
        """Send at most once per cooldown for the same key, so a stuck state doesn't spam."""
        now = time.monotonic()
        if now - self._last_sent.get(key, -cooldown_s) < cooldown_s:
            log.info("(повтор подавлен) %s", text.replace("\n", " | "))
            return
        self._last_sent[key] = now
        self.send(text, photo)

    def reset(self, key: str) -> None:
        self._last_sent.pop(key, None)


def desktop_alert(title: str, message: str) -> None:
    """macOS notification and sound; silently does nothing elsewhere."""
    if platform.system() != "Darwin":
        return
    safe = message.replace('"', "'")
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe}" with title "{title}" sound name "Glass"'],
        check=False,
    )
    for _ in range(3):
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
