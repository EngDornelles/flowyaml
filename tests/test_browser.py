"""Headless browser smoke tests.

Every test loads a generated ``file://`` document with an interception rule
that aborts and records any request leaving the file scheme, so a passing run
is also proof that the artifact is offline complete.

Skipped when playwright or its chromium build is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import flowyaml

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


class Session:
    """A loaded page plus the evidence collected while it loaded."""

    def __init__(self, page, offenders, errors):
        self.page = page
        self.offenders = offenders
        self.errors = errors


def _block_the_network(page, offenders):
    def route(handler):
        if handler.request.url.startswith("file://"):
            handler.continue_()
        else:
            offenders.append(handler.request.url)
            handler.abort()

    page.route("**/*", route)


@pytest.fixture
def session(browser, parity_document: Path):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    offenders: list[str] = []
    errors: list[str] = []

    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(f"{message.type}: {message.text}")
        if message.type == "error"
        else None,
    )
    _block_the_network(page, offenders)

    page.goto(parity_document.as_uri())
    page.wait_for_selector("#fy-suite[data-fy-ready='true']", timeout=30_000)
    page.wait_for_selector("#fy-suite .fy-node", timeout=30_000)
    try:
        yield Session(page, offenders, errors)
    finally:
        page.close()


def _transform(page) -> str:
    return page.evaluate(
        "() => document.querySelector('#fy-suite .fy-viewport').getAttribute('transform')"
    )


def _scale(page) -> float:
    return float(_transform(page).split("scale(")[1].rstrip(")"))


def _translate(page) -> str:
    return _transform(page).split(")")[0]


def test_document_renders_without_any_network_request(session):
    assert session.offenders == []
    assert session.errors == []


def test_all_seven_node_types_render(session):
    page = session.page
    for node_type in (
        "startEvent",
        "endEvent",
        "intermediateEvent",
        "gateway",
        "subprocess",
        "state",
        "task",
    ):
        assert page.locator(f"#fy-suite .fy-node--{node_type}").count() >= 1, node_type


def test_edges_labels_and_association_styling_render(session):
    page = session.page
    assert page.locator("#fy-suite .fy-edge").count() == 13
    assert page.locator("#fy-suite .fy-edge--dotted").count() == 2
    assert page.locator("#fy-suite .fy-chip").count() >= 3
    assert page.locator("#fy-suite .fy-chip--detailed").count() >= 2


def test_labels_are_text_not_markup(session):
    assert session.page.evaluate("() => window.__flowyaml_pwned === undefined")
    assert session.page.locator("#fy-suite .fy-node-text").first.text_content()


def test_subprocess_click_switches_the_embedded_model(session):
    page = session.page
    page.locator('#fy-suite [data-fy-ref="procurement"]').click()
    page.wait_for_function("() => location.hash === '#model=procurement'")
    page.wait_for_timeout(600)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Procurement cycle"
    assert page.locator("#fy-suite .fy-crumb").count() == 2
    assert session.offenders == []


def test_keyboard_activation_opens_a_subprocess(session):
    page = session.page
    page.evaluate("location.hash = 'model=procurement'")
    page.wait_for_timeout(700)
    page.locator('#fy-suite [data-fy-ref="quotation"]').focus()
    assert (
        page.evaluate("() => document.activeElement.getAttribute('data-fy-ref')")
        == "quotation"
    )
    page.keyboard.press("Enter")
    page.wait_for_function("() => location.hash === '#model=quotation'")
    page.wait_for_timeout(600)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Quotation and award"


def test_focused_subprocess_shows_a_visible_ring(session):
    page = session.page
    page.locator('#fy-suite [data-fy-ref="procurement"]').focus()
    opacity = page.evaluate(
        """() => {
            const ring = document
              .querySelector('#fy-suite [data-fy-ref="procurement"] .fy-node-focus');
            return window.getComputedStyle(ring).opacity;
        }"""
    )
    assert float(opacity) == 1.0


def test_browser_history_walks_the_levels(session):
    page = session.page
    page.locator('#fy-suite [data-fy-ref="procurement"]').click()
    page.wait_for_function("() => location.hash === '#model=procurement'")
    page.wait_for_timeout(500)
    page.locator('#fy-suite [data-fy-ref="quotation"]').click()
    page.wait_for_function("() => location.hash === '#model=quotation'")
    page.wait_for_timeout(500)

    page.go_back()
    page.wait_for_timeout(700)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Procurement cycle"
    page.go_forward()
    page.wait_for_timeout(700)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Quotation and award"


def test_unreferenced_subprocess_is_a_destination_not_a_control(session):
    page = session.page
    page.evaluate("location.hash = 'model=dispatch'")
    page.wait_for_timeout(800)
    destination = page.locator("#fy-suite .fy-node--destination")
    assert destination.count() == 1
    assert page.locator("#fy-suite .fy-node--navigable").count() == 0
    assert destination.first.get_attribute("data-fy-ref") is None


def test_detailed_edge_label_shows_a_tooltip(session):
    page = session.page
    page.locator("#fy-suite .fy-chip--detailed").first.hover()
    page.wait_for_timeout(250)
    tooltip = page.locator("#fy-suite .fy-tooltip")
    assert tooltip.is_visible()
    assert len(tooltip.inner_text()) > 20


def test_state_detail_shows_a_tooltip(session):
    page = session.page
    page.locator('#fy-suite [data-fy-node="awaiting_delivery"]').hover()
    page.wait_for_timeout(250)
    tooltip = page.locator("#fy-suite .fy-tooltip")
    assert tooltip.is_visible()
    assert "delivery window" in tooltip.inner_text()


def test_detail_is_named_on_its_own_element_not_borrowed_from_a_shared_node(session):
    """Regression: one tooltip element cannot describe many elements.

    Every detail carrying node and chip used to point aria-describedby at
    the instance's single tooltip div. At rest that div is empty, so a
    navigable subprocess never announced its own detail; after any hover it
    held a neighbour's text, so the description announced was the wrong
    one. The detail now belongs to the accessible name of the element that
    owns it.
    """
    page = session.page
    page.evaluate("location.hash = 'model=distribution'")
    page.wait_for_timeout(700)

    # Hovering one node loads the shared tooltip with that node's text.
    page.locator('#fy-suite [data-fy-node="awaiting_delivery"]').hover()
    page.wait_for_timeout(250)
    shared = page.locator("#fy-suite .fy-tooltip")
    assert "delivery window" in shared.inner_text()

    # Nothing borrows a description from it, and it is not announced itself.
    assert page.locator("#fy-suite [aria-describedby]").count() == 0
    assert shared.get_attribute("aria-hidden") == "true"

    # A navigable subprocess carries its own detail in its own name.
    control = page.locator('#fy-suite [data-fy-ref="procurement"]')
    name = control.get_attribute("aria-label")
    assert name.startswith("Open subprocess: Procurement cycle")
    assert "returning the item to stock" in name

    # So does a detailed edge chip and a detailed state card.
    assert "reserved immediately" in page.locator(
        "#fy-suite .fy-chip--detailed"
    ).first.get_attribute("aria-label")
    assert "five working days" in page.locator(
        '#fy-suite [data-fy-node="awaiting_delivery"]'
    ).get_attribute("aria-label")


def test_wheel_zoom_is_clamped_to_the_documented_range(session):
    page = session.page
    page.mouse.move(640, 400)
    for _ in range(30):
        page.mouse.wheel(0, -600)
    page.wait_for_timeout(250)
    assert _scale(page) <= 2.6 + 1e-6

    for _ in range(80):
        page.mouse.wheel(0, 600)
    page.wait_for_timeout(250)
    assert _scale(page) >= 0.2 - 1e-6


def test_wheel_zoom_keeps_the_cursor_point_fixed(session):
    page = session.page
    point = {"x": 700, "y": 420}
    before = page.evaluate(
        """(point) => {
            const svg = document.querySelector('#fy-suite .fy-svg');
            const box = svg.getBoundingClientRect();
            const g = document.querySelector('#fy-suite .fy-viewport');
            const m = g.getScreenCTM().inverse();
            const p = new DOMPoint(point.x, point.y).matrixTransform(m);
            return {x: p.x, y: p.y, w: box.width};
        }""",
        point,
    )
    page.mouse.move(point["x"], point["y"])
    page.mouse.wheel(0, -400)
    page.wait_for_timeout(200)
    after = page.evaluate(
        """(point) => {
            const g = document.querySelector('#fy-suite .fy-viewport');
            const m = g.getScreenCTM().inverse();
            const p = new DOMPoint(point.x, point.y).matrixTransform(m);
            return {x: p.x, y: p.y};
        }""",
        point,
    )
    assert abs(after["x"] - before["x"]) < 1.0
    assert abs(after["y"] - before["y"]) < 1.0


def test_pointer_drag_pans_without_navigating(session):
    page = session.page
    before = _translate(page)
    page.mouse.move(700, 500)
    page.mouse.down()
    page.mouse.move(560, 430, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert _translate(page) != before
    assert page.evaluate("location.hash") in ("", "#model=distribution")


def test_toolbar_zoom_and_fit_controls_work(session):
    page = session.page
    page.locator("#fy-suite .fy-btn[aria-label='Zoom in']").click()
    page.wait_for_timeout(200)
    zoomed = _scale(page)
    page.locator("#fy-suite .fy-btn[aria-label='Fit the diagram to the view']").click()
    page.wait_for_timeout(250)
    assert _scale(page) != zoomed
    assert "%" in page.locator("#fy-suite .fy-zoom-readout").inner_text()


def test_keyboard_pan_and_fit_shortcuts(session):
    page = session.page
    page.locator("#fy-suite .fy-svg").focus()
    before = _translate(page)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(150)
    panned = _translate(page)
    assert panned != before
    page.keyboard.press("0")
    page.wait_for_timeout(250)
    assert _translate(page) != panned


def test_breadcrumb_and_back_button_walk_up_a_level(session):
    page = session.page
    page.locator('#fy-suite [data-fy-ref="procurement"]').click()
    page.wait_for_function("() => location.hash === '#model=procurement'")
    page.wait_for_timeout(600)
    page.locator("#fy-suite .fy-btn[aria-label='Go up one flow level']").click()
    page.wait_for_timeout(700)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Material distribution"
    assert page.locator(
        "#fy-suite .fy-btn[aria-label='Go up one flow level']"
    ).is_disabled()


def test_two_fragments_mount_side_by_side(browser, tmp_path, parity_source):
    """Acceptance criterion 7, proved in a real host page."""
    first = flowyaml.render(parity_source, output="fragment", instance_id="fy-left")
    second = flowyaml.render(parity_source, output="fragment", instance_id="fy-right")
    host = tmp_path / "host.html"
    host.write_text(
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        "<style>body{margin:0;font-family:serif;color:#c0392b}"
        ".panel{width:620px;height:420px}</style></head><body>"
        "<h1>Host page heading</h1>"
        f"<div class='panel'>{first}</div>"
        f"<div class='panel'>{second}</div>"
        "</body></html>",
        encoding="utf-8",
    )

    page = browser.new_page(viewport={"width": 1320, "height": 1000})
    offenders: list[str] = []
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    _block_the_network(page, offenders)

    page.goto(host.as_uri())
    page.wait_for_selector("#fy-left[data-fy-ready='true']", timeout=30_000)
    page.wait_for_selector("#fy-right[data-fy-ready='true']", timeout=30_000)
    page.wait_for_selector("#fy-left .fy-node", timeout=30_000)
    page.wait_for_selector("#fy-right .fy-node", timeout=30_000)

    assert offenders == []
    assert errors == []
    assert page.locator("#fy-left .fy-node").count() == 12
    assert page.locator("#fy-right .fy-node").count() == 12
    assert page.evaluate("() => typeof window.ELK") == "function"

    # No style leaked onto the host page.
    assert (
        page.evaluate("() => getComputedStyle(document.querySelector('h1')).color")
        == "rgb(192, 57, 43)"
    )

    # Each instance owns its own hash key, so navigation never crosses over.
    page.locator('#fy-left [data-fy-ref="procurement"]').click()
    page.wait_for_function("() => location.hash.indexOf('fy-left=procurement') >= 0")
    page.wait_for_timeout(800)
    assert page.locator("#fy-left .fy-model-name").inner_text() == "Procurement cycle"
    assert page.locator("#fy-right .fy-model-name").inner_text() == "Material distribution"

    page.locator('#fy-right [data-fy-ref="dispatch"]').click()
    page.wait_for_function("() => location.hash.indexOf('fy-right=dispatch') >= 0")
    page.wait_for_timeout(800)
    assert page.locator("#fy-left .fy-model-name").inner_text() == "Procurement cycle"
    assert page.locator("#fy-right .fy-model-name").inner_text() == "Dispatch and handover"

    page.close()


def test_hostile_labels_stay_inert_in_a_browser(browser, tmp_path, fixtures_dir):
    source = (fixtures_dir / "hostile_labels.yaml").read_text(encoding="utf-8")
    target = tmp_path / "hostile.html"
    target.write_text(flowyaml.render(source, instance_id="fy-hostile"), encoding="utf-8")

    page = browser.new_page()
    errors: list[str] = []
    offenders: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    _block_the_network(page, offenders)

    page.goto(target.as_uri())
    page.wait_for_selector("#fy-hostile .fy-node", timeout=30_000)

    assert page.evaluate("() => window.__flowyaml_pwned === undefined")
    assert page.locator("#fy-hostile img").count() == 0
    assert page.locator("#fy-hostile script").count() == 0
    rendered = page.locator("#fy-hostile .fy-node-text").first.text_content()
    assert "script" in rendered.lower()
    assert errors == []
    assert offenders == []
    page.close()


def test_a_single_node_model_still_lays_out(browser, tmp_path, fixtures_dir):
    source = (fixtures_dir / "no_edges.yaml").read_text(encoding="utf-8")
    target = tmp_path / "lonely.html"
    target.write_text(flowyaml.render(source, instance_id="fy-lonely"), encoding="utf-8")

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(target.as_uri())
    page.wait_for_selector("#fy-lonely .fy-node", timeout=30_000)
    assert page.locator("#fy-lonely .fy-node").count() == 1
    assert page.locator("#fy-lonely .fy-edge").count() == 0
    assert errors == []
    page.close()


def test_a_merge_gateway_without_a_label_renders(browser, tmp_path, fixtures_dir):
    source = (fixtures_dir / "merge_gateway.yaml").read_text(encoding="utf-8")
    target = tmp_path / "merge.html"
    target.write_text(flowyaml.render(source, instance_id="fy-merge"), encoding="utf-8")

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(target.as_uri())
    page.wait_for_selector("#fy-merge .fy-node", timeout=30_000)
    assert page.locator("#fy-merge .fy-node--gateway").count() == 1
    assert errors == []
    page.close()


def test_touch_tap_opens_a_subprocess(browser, parity_document: Path):
    """Acceptance criterion 5 on a touch-capable browser."""
    context = browser.new_context(
        viewport={"width": 900, "height": 700}, has_touch=True
    )
    page = context.new_page()
    errors: list[str] = []
    offenders: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    _block_the_network(page, offenders)

    page.goto(parity_document.as_uri())
    page.wait_for_selector("#fy-suite .fy-node", timeout=30_000)
    page.locator('#fy-suite [data-fy-ref="procurement"]').tap()
    page.wait_for_function("() => location.hash === '#model=procurement'")
    page.wait_for_timeout(700)
    assert page.locator("#fy-suite .fy-model-name").inner_text() == "Procurement cycle"
    assert errors == []
    assert offenders == []
    context.close()


def test_print_stylesheet_hides_the_controls(session):
    page = session.page
    page.emulate_media(media="print")
    page.wait_for_timeout(150)
    assert page.locator("#fy-suite .fy-controls").is_hidden()
    assert page.locator("#fy-suite .fy-hint").is_hidden()
    assert page.locator("#fy-suite .fy-node").first.is_visible()
    page.emulate_media(media="screen")


# --------------------------------------------------------------------------- #
# imported sources
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def imported_document(tmp_path_factory, examples_dir: Path) -> Path:
    """A BPMN file rendered straight from the importer, with no YAML step."""
    diagram = flowyaml.read_bpmn(examples_dir / "order_handling.bpmn")
    target = tmp_path_factory.mktemp("imported") / "order.html"
    target.write_text(
        flowyaml.render(diagram, instance_id="fy-import"), encoding="utf-8"
    )
    return target


def test_an_imported_process_draws_offline(browser, imported_document: Path):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    offenders: list[str] = []
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(f"{message.type}: {message.text}")
        if message.type == "error"
        else None,
    )
    _block_the_network(page, offenders)
    try:
        page.goto(imported_document.as_uri())
        page.wait_for_selector("#fy-import[data-fy-ready='true']", timeout=30_000)
        page.wait_for_selector("#fy-import .fy-node", timeout=30_000)

        assert offenders == []
        assert errors == []
        assert page.locator("#fy-import .fy-node").count() == 10

        # The expanded sub-process opens its own level, with no network.
        page.locator("#fy-import [role='button']").first.click()
        page.wait_for_function(
            "() => document.querySelector('#fy-import').dataset.fyModel"
            " === 'SubProcess_procurement'",
            timeout=15_000,
        )
        assert offenders == []
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# presentation: scheme, drawer and stripe
# --------------------------------------------------------------------------- #


def _mounted(browser, tmp_path, source, name, **options):
    """Render `source` with `options` and return a loaded, offline page."""
    target = tmp_path / f"{name}.html"
    target.write_text(
        flowyaml.render(source, instance_id=name, **options), encoding="utf-8"
    )
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    offenders: list[str] = []
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(f"{message.type}: {message.text}")
        if message.type == "error"
        else None,
    )
    _block_the_network(page, offenders)
    page.goto(target.as_uri())
    page.wait_for_selector(f"#{name}[data-fy-ready='true']", timeout=30_000)
    page.wait_for_selector(f"#{name} .fy-node", timeout=30_000)
    return page, offenders, errors


def _background(page, selector: str) -> str:
    return page.evaluate(
        "(selector) => getComputedStyle(document.querySelector(selector))"
        ".backgroundColor",
        selector,
    )


def test_the_dark_palette_follows_the_readers_machine(browser, tmp_path, parity_source):
    """One artifact, both schemes, decided at view time and never fetched."""
    page, offenders, errors = _mounted(browser, tmp_path, parity_source, "fy-scheme")
    try:
        page.emulate_media(color_scheme="light")
        page.wait_for_timeout(120)
        light = _background(page, "#fy-scheme")

        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(120)
        dark = _background(page, "#fy-scheme")

        assert light != dark, "the dark tokens never reached the instance"
        assert offenders == []
        assert errors == []
    finally:
        page.close()


def test_a_pinned_scheme_ignores_the_machine(browser, tmp_path, parity_source):
    page, _, errors = _mounted(
        browser, tmp_path, parity_source, "fy-pinned", scheme="light"
    )
    try:
        page.emulate_media(color_scheme="light")
        page.wait_for_timeout(120)
        light = _background(page, "#fy-pinned")

        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(120)
        assert _background(page, "#fy-pinned") == light
        assert errors == []
    finally:
        page.close()


def test_the_drawer_lists_and_opens_the_next_levels(session):
    page = session.page
    drawer = page.locator("#fy-suite .fy-next")
    assert drawer.is_visible()
    # Closed until asked: it costs one line of height on arrival.
    assert page.locator("#fy-suite .fy-next-item").first.is_hidden()

    page.locator("#fy-suite .fy-next-summary").click()
    page.wait_for_timeout(150)
    items = page.locator("#fy-suite .fy-next-item")
    assert items.count() == 2  # procurement and dispatch

    items.first.click()
    page.wait_for_function("() => location.hash === '#model=procurement'")
    page.wait_for_timeout(600)
    assert page.locator("#fy-suite .fy-model-name").inner_text() != "Material distribution"

    # A fresh level gets a fresh drawer, closed again.
    assert page.locator("#fy-suite .fy-next").get_attribute("open") is None
    page.locator("#fy-suite .fy-btn[aria-label='Go up one flow level']").click()
    page.wait_for_timeout(700)


def test_a_destination_card_is_not_a_next_step(session):
    """dispatch holds a subprocess with no ref: a card, not a control, so the
    drawer has nothing to offer and does not take the line."""
    page = session.page
    page.locator('#fy-suite [data-fy-ref="dispatch"]').click()
    page.wait_for_function("() => location.hash === '#model=dispatch'")
    page.wait_for_timeout(600)
    assert page.locator("#fy-suite .fy-next").is_hidden()
    page.locator("#fy-suite .fy-btn[aria-label='Go up one flow level']").click()
    page.wait_for_timeout(700)


def test_the_stripe_shows_the_level_above_and_returns_to_it(
    browser, tmp_path, parity_source
):
    page, offenders, errors = _mounted(
        browser, tmp_path, parity_source, "fy-stripe", levels="snapshot"
    )
    try:
        # At the top there is nothing above, so the stripe stays empty.
        assert page.locator("#fy-stripe .fy-ancestor").count() == 0
        assert page.locator("#fy-stripe .fy-breadcrumb").is_hidden()
        assert page.locator("#fy-stripe .fy-level").inner_text().endswith("01")

        page.locator('#fy-stripe [data-fy-ref="procurement"]').click()
        page.wait_for_function("() => location.hash === '#model=procurement'")
        page.wait_for_timeout(800)

        ancestors = page.locator("#fy-stripe .fy-ancestor")
        assert ancestors.count() == 1
        assert page.locator("#fy-stripe .fy-level").inner_text().endswith("02")

        # The snapshot is a real copy of the diagram that was left behind.
        assert page.locator("#fy-stripe .fy-thumb svg").count() == 1

        page.locator("#fy-stripe .fy-ancestor-btn").click()
        page.wait_for_function("() => location.hash === '#model=distribution'")
        page.wait_for_timeout(700)
        assert page.locator("#fy-stripe .fy-ancestor").count() == 0

        assert offenders == []
        assert errors == []
    finally:
        page.close()


def test_the_snapshot_does_not_steal_the_live_markers(
    browser, tmp_path, parity_source
):
    """Two SVGs on one page must not share ids, or url(#id) cross-wires."""
    page, _, errors = _mounted(
        browser, tmp_path, parity_source, "fy-ids", levels="snapshot"
    )
    try:
        page.locator('#fy-ids [data-fy-ref="procurement"]').click()
        page.wait_for_function("() => location.hash === '#model=procurement'")
        page.wait_for_timeout(800)

        duplicates = page.evaluate(
            """() => {
                const seen = {};
                const clashes = [];
                document.querySelectorAll('#fy-ids [id]').forEach((node) => {
                    if (seen[node.id]) { clashes.push(node.id); }
                    seen[node.id] = true;
                });
                return clashes;
            }"""
        )
        assert duplicates == []
        # The live diagram still paints its arrowheads.
        assert page.locator("#fy-ids .fy-edge-path").count() > 0
        assert errors == []
    finally:
        page.close()


def test_translated_chrome_reaches_the_controls(browser, tmp_path, parity_source):
    page, _, errors = _mounted(
        browser,
        tmp_path,
        parity_source,
        "fy-idiom",
        strings={
            "back": "Voltar",
            "backAria": "Subir um nivel",
            "nextSteps": "Explorar os proximos passos",
        },
    )
    try:
        assert page.locator("#fy-idiom .fy-btn[aria-label='Subir um nivel']").count() == 1
        assert "Explorar os proximos passos" in page.locator(
            "#fy-idiom .fy-next-summary"
        ).inner_text()
        assert errors == []
    finally:
        page.close()
