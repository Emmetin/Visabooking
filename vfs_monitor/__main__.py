"""Run: python -m vfs_monitor [--once | --login | --test-telegram]"""

import argparse
import logging
import random
import sys
import time

from playwright.sync_api import BrowserContext, sync_playwright

from .checker import OptionNotFound, check_once, current_state, wait_for_user
from .config import Config, load_config
from .notify import Notifier, desktop_alert
from .parsing import PageState, SlotStatus

log = logging.getLogger("vfs_monitor")

HOUR = 3600
BLOCKED_BACKOFF_S = 30 * 60
MAX_ERROR_BACKOFF_S = 30 * 60


def open_browser(p, cfg: Config) -> BrowserContext:
    kwargs = dict(user_data_dir=str(cfg.profile_dir), headless=False, viewport=None, locale="ru-RU")
    if cfg.browser_channel:
        try:
            return p.chromium.launch_persistent_context(channel=cfg.browser_channel, **kwargs)
        except Exception as e:
            log.warning("Не удалось запустить %s (%s), пробую встроенный Chromium", cfg.browser_channel, e)
    return p.chromium.launch_persistent_context(**kwargs)


def ask_user_to_login(page, notifier: Notifier, state: PageState) -> None:
    what = "войдите в аккаунт VFS" if state is PageState.LOGIN else "пройдите проверку «я не робот»"
    notifier.send_throttled(
        "login",
        f"⚠️ Нужно действие: {what} в открытом окне браузера на Mac. Мониторинг продолжится сам.",
        cooldown_s=HOUR,
    )
    desktop_alert("VFS монитор", f"Нужно: {what}")
    if wait_for_user(page):
        notifier.reset("login")
        log.info("Вход выполнен, продолжаю")


def handle_found(result, notifier: Notifier) -> bool:
    notifier.send(
        "🟢 ПОЯВИЛСЯ СЛОТ во французском визовом центре (Москва)!\n"
        f"{result.snippet}\n\n"
        "Срочно подойдите к Mac и завершите запись в открытом окне браузера.",
        photo=result.screenshot,
    )
    desktop_alert("VFS: есть слот!", result.snippet or "Завершите запись в браузере")
    print("\n" + "=" * 60)
    print("ЕСТЬ СЛОТ! Завершите запись в окне браузера (капча и подтверждение — вручную).")
    print("Мониторинг на паузе, чтобы не сбить вашу форму.")
    answer = input("Когда закончите: Enter — выйти, 'c' + Enter — продолжить мониторинг: ")
    return answer.strip().lower() == "c"


def run(cfg: Config, notifier: Notifier, once: bool) -> None:
    with sync_playwright() as p:
        ctx = open_browser(p, cfg)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        notifier.send("▶️ Мониторинг слотов VFS (Франция, Москва) запущен.")
        errors = 0
        while True:
            delay = random.uniform(cfg.interval_min, cfg.interval_max) * 60
            try:
                result = check_once(page, cfg)
                errors = 0
                if result.state in (PageState.LOGIN, PageState.CHALLENGE):
                    ask_user_to_login(page, notifier, result.state)
                    delay = 5
                elif result.state is PageState.BLOCKED:
                    notifier.send_throttled(
                        "blocked", "⛔ VFS ограничил доступ (слишком частые запросы). Пауза 30 минут.", HOUR
                    )
                    delay = BLOCKED_BACKOFF_S
                elif result.slots is SlotStatus.AVAILABLE:
                    if not handle_found(result, notifier):
                        return
                    delay = 5
                elif result.slots is SlotStatus.NONE:
                    log.info("Слотов нет: %s", result.snippet)
                else:
                    notifier.send_throttled(
                        "unknown",
                        "❓ Не смог распознать ответ сайта — посмотрите скриншот. "
                        "Возможно, слот есть или сайт изменился.",
                        HOUR,
                        photo=result.screenshot,
                    )
            except OptionNotFound as e:
                notifier.send_throttled(
                    "option",
                    f"⚙️ В выпадающем списке №{e.index + 1} нет варианта по шаблону «{e.wanted}».\n"
                    "Доступные варианты:\n- " + "\n- ".join(e.available) +
                    "\n\nИсправьте CENTRE / CATEGORY / SUBCATEGORY в .env и перезапустите.",
                    HOUR,
                )
                if once:
                    return
                delay = 10 * 60
            except Exception as e:
                errors += 1
                log.exception("Ошибка проверки")
                if errors == 3:
                    notifier.send(f"⚠️ 3 ошибки подряд: {e!s:.300}")
                delay = min(delay * 2 ** (errors - 1), MAX_ERROR_BACKOFF_S)

            if once:
                return
            log.info("Следующая проверка через %.1f мин", delay / 60)
            time.sleep(delay)


def login_only(cfg: Config) -> None:
    with sync_playwright() as p:
        ctx = open_browser(p, cfg)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(cfg.login_url)
        input("Войдите в аккаунт в открытом окне, затем нажмите Enter здесь… ")
        print("Состояние:", current_state(page).value, "— сессия сохранена в browser_profile/")
        ctx.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    parser = argparse.ArgumentParser(description="Мониторинг слотов VFS Global")
    parser.add_argument("--once", action="store_true", help="одна проверка и выход")
    parser.add_argument("--login", action="store_true", help="только открыть браузер для входа")
    parser.add_argument("--test-telegram", action="store_true", help="отправить тестовое сообщение")
    args = parser.parse_args()

    cfg = load_config()
    notifier = Notifier(cfg.telegram_token, cfg.telegram_chat_id)
    if not notifier.enabled:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — уведомления только в консоли")

    if args.test_telegram:
        if not notifier.enabled:
            sys.exit("Заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env")
        notifier.send("✅ Тест: уведомления от VFS монитора работают.")
        return
    if args.login:
        login_only(cfg)
        return
    try:
        run(cfg, notifier, args.once)
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
