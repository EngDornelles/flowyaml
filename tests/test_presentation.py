"""Presentation options: colour scheme, level mode, UI strings and language.

None of these change the graph. They change the furniture around it: which
palette the artifact wears, how it shows the reader where they are, and which
language it speaks when it speaks for itself.
"""

from __future__ import annotations

import json
import re

import pytest

import flowyaml
from flowyaml.renderer import UI_STRINGS


def payload_of(html: str) -> dict:
    match = re.search(
        r'<script id="[^"]+-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "the graph payload script is missing"
    return json.loads(match.group(1))


# --------------------------------------------------------------- colour scheme


def test_both_palettes_ship_in_every_document(parity_source):
    """One artifact, two palettes: the reader's machine picks at view time."""
    html = flowyaml.render(parity_source, instance_id="fy-scheme")
    assert "@media (prefers-color-scheme: dark)" in html
    assert '#fy-scheme[data-fy-scheme="dark"]' in html
    # A token that differs between the tables proves the dark one is real.
    assert flowyaml.THEMES[flowyaml.DEFAULT_THEME]["canvas"] in html
    assert flowyaml.DARK_THEMES[flowyaml.DEFAULT_THEME]["canvas"] in html


def test_auto_scheme_declares_both_to_the_browser(parity_source):
    html = flowyaml.render(parity_source, instance_id="fy-auto")
    assert '<meta name="color-scheme" content="light dark">' in html
    assert '<html lang="en" data-fy-scheme="auto">' in html


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_pinned_scheme_reaches_the_page_and_the_mount(parity_source, scheme):
    html = flowyaml.render(parity_source, scheme=scheme, instance_id="fy-pin")
    assert f'<meta name="color-scheme" content="{scheme}">' in html
    assert f'data-fy-scheme="{scheme}"' in html
    # Pinning one scheme still ships the other's tokens: the option decides
    # what the page uses, not what it contains.
    assert "@media (prefers-color-scheme: dark)" in html


def test_the_forced_dark_rule_comes_after_the_media_rule(parity_source):
    """Equal specificity, so source order is what settles a pinned instance."""
    html = flowyaml.render(parity_source, instance_id="fy-order")
    media = html.index("@media (prefers-color-scheme: dark)")
    forced = html.index('#fy-order[data-fy-scheme="dark"]')
    assert media < forced


def test_print_repoints_the_tokens_so_paper_is_one_palette(parity_source):
    html = flowyaml.render(parity_source, scheme="dark", instance_id="fy-print")
    print_block = html[html.index("@media print"):]
    assert "--fy-ink: #000000;" in print_block
    assert "color-scheme: light;" in print_block


def test_an_unknown_scheme_is_refused(parity_source):
    with pytest.raises(flowyaml.FlowYAMLOptionError) as caught:
        flowyaml.render(parity_source, scheme="sepia")
    assert "sepia" in str(caught.value)


def test_the_dark_table_is_looked_up_the_same_way_the_light_one_is():
    """An absent dark table means "this theme looks the same either way", and
    an unknown theme fails here exactly as it fails for the light lookup."""
    from flowyaml.themes import get_dark_theme

    assert get_dark_theme(flowyaml.DEFAULT_THEME)
    with pytest.raises(flowyaml.FlowYAMLOptionError):
        get_dark_theme("not_a_theme")


def test_the_dark_table_only_names_tokens_the_light_one_defines():
    """A dark-only token would be a variable nothing in the stylesheet reads."""
    light = set(flowyaml.THEMES[flowyaml.DEFAULT_THEME])
    dark = set(flowyaml.DARK_THEMES[flowyaml.DEFAULT_THEME])
    assert dark <= light, sorted(dark - light)


# ------------------------------------------------------------------- levels


def test_breadcrumb_is_the_default(parity_source):
    html = flowyaml.render(parity_source, instance_id="fy-levels")
    assert 'data-fy-levels="breadcrumb"' in html
    assert payload_of(html)["levels"] == "breadcrumb"


def test_snapshot_is_opt_in_and_reaches_the_runtime(parity_source):
    html = flowyaml.render(parity_source, levels="snapshot", instance_id="fy-snap")
    assert 'data-fy-levels="snapshot"' in html
    assert payload_of(html)["levels"] == "snapshot"
    assert '#fy-snap[data-fy-levels="snapshot"]' in html


def test_an_unknown_level_mode_is_refused(parity_source):
    with pytest.raises(flowyaml.FlowYAMLOptionError) as caught:
        flowyaml.render(parity_source, levels="minimap")
    assert "minimap" in str(caught.value)
    assert "breadcrumb" in str(caught.value)


# ---------------------------------------------------------------- UI strings


def test_strings_default_to_the_packaged_table(parity_source):
    data = payload_of(flowyaml.render(parity_source, instance_id="fy-str"))
    assert data["strings"] == dict(UI_STRINGS)


def test_an_override_merges_rather_than_replaces(parity_source):
    html = flowyaml.render(
        parity_source,
        strings={"back": "Voltar", "fit": "Ajustar"},
        instance_id="fy-pt",
    )
    strings = payload_of(html)["strings"]
    assert strings["back"] == "Voltar"
    assert strings["fit"] == "Ajustar"
    # Everything not named keeps its default, so one key is one key.
    assert strings["zoomIn"] == UI_STRINGS["zoomIn"]
    assert len(strings) == len(UI_STRINGS)


def test_every_string_the_runtime_reads_is_declared():
    """A key the runtime reads but the table omits would be unoverridable."""
    runtime = flowyaml.renderer.read_asset("runtime.js")
    used = set(re.findall(r"strings\.([A-Za-z]+)", runtime))
    assert used, "the runtime reads no strings at all, which cannot be right"
    assert used <= set(UI_STRINGS), sorted(used - set(UI_STRINGS))


def test_an_unknown_string_key_is_refused_not_ignored(parity_source):
    """A silent typo would surface as English in the middle of a translation."""
    with pytest.raises(flowyaml.FlowYAMLOptionError) as caught:
        flowyaml.render(parity_source, strings={"bakc": "Voltar"})
    assert "bakc" in str(caught.value)


def test_an_empty_string_value_is_refused(parity_source):
    with pytest.raises(flowyaml.FlowYAMLOptionError):
        flowyaml.render(parity_source, strings={"back": "   "})


def test_strings_must_be_a_mapping(parity_source):
    with pytest.raises(flowyaml.FlowYAMLOptionError):
        flowyaml.render(parity_source, strings=[("back", "Voltar")])


def test_translated_strings_survive_into_the_page(parity_source):
    html = flowyaml.render(
        parity_source,
        strings={"hint": "Arraste para mover · role para ampliar"},
        instance_id="fy-hint",
    )
    # ensure_ascii keeps the payload transportable whatever the host declares.
    html.encode("ascii")
    assert "Arraste para mover" in json.dumps(payload_of(html)["strings"])


# ------------------------------------------------------------------ language


def test_the_document_language_defaults_to_english(parity_source):
    assert '<html lang="en"' in flowyaml.render(parity_source)


def test_meta_lang_travels_with_the_source():
    source = """
meta:
  id: cozinha
  name: O que tem pra hoje?
  lang: pt-BR
nodes:
  - id: fome
    type: startEvent
    label: Bateu a fome
edges: []
"""
    assert '<html lang="pt-BR"' in flowyaml.render(source)


def test_the_render_option_beats_the_source(parity_source):
    source = """
meta:
  id: flow
  lang: pt-BR
nodes:
  - id: a
    type: startEvent
    label: Start
edges: []
"""
    assert '<html lang="es-AR"' in flowyaml.render(source, lang="es-AR")


def test_a_language_tag_that_is_not_one_is_refused(parity_source):
    with pytest.raises(flowyaml.FlowYAMLOptionError):
        flowyaml.render(parity_source, lang='en" onload="alert(1)')


def test_a_fragment_carries_no_document_language(parity_source):
    """A fragment inherits the host page, so it never writes <html lang>."""
    fragment = flowyaml.render(parity_source, output="fragment", lang="pt-BR")
    assert "<html" not in fragment
