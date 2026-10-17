import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    base_url: str
    telegram_token: str
    telegram_chat_id: str
    # Regexes matched against dropdown options, in the order the dropdowns appear.
    selections: list[str]
    interval_min: float
    interval_max: float
    profile_dir: Path
    screenshots_dir: Path
    browser_channel: str

    @property
    def dashboard_url(self) -> str:
        return f"{self.base_url}/dashboard"

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/login"


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    env = os.environ.get

    selections = [
        env("CENTRE", "Москв|Moscow"),
        env("CATEGORY", "Кратк|Short|Шенген|Schengen"),
        env("SUBCATEGORY", "Туриз|Touris"),
    ]
    interval_min = max(2.0, float(env("INTERVAL_MIN_MINUTES", "4")))
    interval_max = max(interval_min, float(env("INTERVAL_MAX_MINUTES", "7")))

    return Config(
        base_url=env("VFS_BASE_URL", "https://visa.vfsglobal.com/rus/ru/fra").rstrip("/"),
        telegram_token=env("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=env("TELEGRAM_CHAT_ID", ""),
        selections=[s for s in selections if s.strip()],
        interval_min=interval_min,
        interval_max=interval_max,
        profile_dir=ROOT / "browser_profile",
        screenshots_dir=ROOT / "screenshots",
        browser_channel=env("BROWSER_CHANNEL", "chrome"),
    )
