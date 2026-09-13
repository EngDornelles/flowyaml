"""Headless proof that an edited YAML file redraws an open page.

The unit tests show the host answering with the new graph. This one shows the
part that matters to whoever is editing: a page that is already open, with no
reload, follows the file. It also pins the file:// boundary, where the same
page must say plainly that it cannot fetch anything.

Skipped when playwright or its chromium build is unavailable.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import flowyaml
from flowyaml.live import create_server

pytestmark = pytest.mark.browser

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed"
)


@pytest.fixture(scope="module")
def browser():
    try:
        with playwright_api.sync_playwright() as driver:
            try:
                instance = driver.chromium.launch()
            except Exception as error:  # pragma: no cover - environment dependent
                pytest.skip(f"chromium is unavailable: {error}")
            yield instance
            instance.close()
    except Exception as error:  # pragma: no cover - environment dependent
        pytest.skip(f"playwright could not start: {error}")


@pytest.fixture
def served(tmp_path: Path, parity_source: str):
    """A running host and the YAML file it is linked to."""
    source = tmp_path / "flow.yaml"
    source.write_text(parity_source, encoding="utf-8")

    server = create_server(source, port=0, poll_ms=200)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.url, source
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_an_open_page_follows_the_yaml_file(browser, served):
    url, source = served
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(url)
        page.wait_for_selector(".fy-root[data-fy-ready='true']", timeout=30_000)
        page.wait_for_selector(".fy-node", timeout=30_000)

        assert page.locator(".fy-model-name").inner_text() == "Material distribution"
        drawn = page.locator(".fy-node").count()
        assert drawn > 0

        # The edit an author would make, saved while the page stays open.
        source.write_text(
            source.read_text(encoding="utf-8").replace(
                "name: Material distribution", "name: Renamed while open", 1
            ),
            encoding="utf-8",
        )

        page.wait_for_function(
            "() => document.querySelector('.fy-model-name').textContent"
            " === 'Renamed while open'",
            timeout=15_000,
        )
        # The title changes as soon as the new graph is adopted; the drawing
        # follows once the layout engine has run again.
        page.wait_for_function(
            f"() => document.querySelectorAll('.fy-node').length === {drawn}",
            timeout=15_000,
        )
        assert errors == []
    finally:
        page.close()


def test_a_broken_save_is_reported_on_the_canvas(browser, served):
    url, source = served
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    try:
        page.goto(url)
        page.wait_for_selector(".fy-node", timeout=30_000)

        source.write_text("meta:\n  id: broken\nnodes: []\n", encoding="utf-8")

        page.wait_for_selector(".fy-empty:not([hidden])", timeout=15_000)
        message = page.locator(".fy-empty").inner_text()
        assert "validation" in message.lower()
    finally:
        page.close()


def test_a_linked_page_opened_from_disk_says_why_it_is_empty(
    browser, tmp_path: Path, parity_source: str
):
    """A browser refuses a fetch from file://, and the page must say so."""
    document = tmp_path / "linked.html"
    document.write_text(
        flowyaml.render(
            parity_source,
            data="url",
            data_url="/flowyaml/data.json",
            instance_id="fy-file",
        ),
        encoding="utf-8",
    )
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    try:
        page.goto(document.as_uri())
        page.wait_for_selector("#fy-file .fy-empty:not([hidden])", timeout=30_000)
        message = page.locator("#fy-file .fy-empty").inner_text()
        assert "http" in message.lower()
        assert "flowyaml serve" in message
    finally:
        page.close()
