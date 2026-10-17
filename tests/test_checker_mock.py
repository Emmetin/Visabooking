"""Runs check_once against a local mock of the VFS booking form (no real site involved)."""

import http.server
import os
import threading
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from vfs_monitor.checker import OptionNotFound, check_once  # noqa: E402
from vfs_monitor.config import load_config  # noqa: E402
from vfs_monitor.parsing import PageState, SlotStatus  # noqa: E402

MOCK_PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<button id="new">Записаться</button>
<div id="form" hidden>
  <mat-select data-opts="Визовый центр Франции, Москва|Визовый центр Франции, Санкт-Петербург">Центр</mat-select>
  <mat-select data-opts="Краткосрочная виза|Долгосрочная виза">Категория</mat-select>
  <mat-select data-opts="Туризм|Бизнес">Подкатегория</mat-select>
  <div id="msg"></div>
</div>
<div id="overlay"></div>
<script>
const RESULT = location.pathname.split("/")[1];
let picked = 0;
document.getElementById("new").onclick = () => { document.getElementById("form").hidden = false; };
document.querySelectorAll("mat-select").forEach(sel => sel.onclick = () => {
  const overlay = document.getElementById("overlay");
  overlay.innerHTML = "";
  sel.dataset.opts.split("|").forEach(o => {
    const el = document.createElement("mat-option");
    el.textContent = o;
    el.onclick = () => {
      overlay.innerHTML = ""; sel.textContent = o;
      if (++picked === 3) setTimeout(() => document.getElementById("msg").textContent =
        RESULT === "yes" ? "Earliest available slot for Tourism is : 24-11-2026"
                         : "No appointment slots are currently available", 500);
    };
    overlay.appendChild(el);
  });
});
</script></body></html>"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    for result in ("yes", "no"):
        (root / result).mkdir()
        (root / result / "dashboard").write_text(MOCK_PAGE, encoding="utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def guess_type(self, path):
            return "text/html"

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        # PLAYWRIGHT_CHROMIUM lets CI point at a pre-installed browser build
        browser = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        yield browser.new_page()
        browser.close()


def run_check(page, server, tmp_path, result, **overrides):
    cfg = replace(load_config(), base_url=f"{server}/{result}", screenshots_dir=tmp_path, **overrides)
    return check_once(page, cfg)


def test_finds_slot(page, server, tmp_path):
    res = run_check(page, server, tmp_path, "yes")
    assert res.state is PageState.OK
    assert res.slots is SlotStatus.AVAILABLE
    assert "24-11-2026" in res.snippet
    assert res.screenshot and res.screenshot.exists()


def test_no_slot(page, server, tmp_path):
    res = run_check(page, server, tmp_path, "no")
    assert res.slots is SlotStatus.NONE


def test_wrong_option_reports_choices(page, server, tmp_path):
    with pytest.raises(OptionNotFound) as e:
        run_check(page, server, tmp_path, "no", selections=["Казань"])
    assert "Визовый центр Франции, Москва" in e.value.available
