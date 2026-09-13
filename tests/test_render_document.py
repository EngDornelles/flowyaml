"""Standalone document output: structure, payload, escaping and options."""

from __future__ import annotations

import json
import re

import pytest

import flowyaml
from flowyaml.renderer import LAYOUT_OPTIONS


def payload_of(html: str) -> dict:
    match = re.search(
        r'<script id="[^"]+-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "the graph payload script is missing"
    return json.loads(match.group(1))


def test_document_has_a_complete_html_skeleton(parity_source):
    html = flowyaml.render(parity_source, instance_id="fy-doc")
    assert html.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in html
    assert '<meta name="viewport"' in html
    assert f'<meta name="generator" content="flowyaml {flowyaml.__version__}">' in html
    assert "<title>Material distribution</title>" in html
    assert html.rstrip().endswith("</html>")
    assert html.count("<body>") == 1


def test_document_carries_style_data_engine_and_runtime(parity_source):
    html = flowyaml.render(parity_source, instance_id="fy-doc")
    assert "<style>" in html
    assert '<div id="fy-doc" class="fy-root"' in html
    assert '<script id="fy-doc-data" type="application/json">' in html
    assert "elkjs 0.9.3" in html
    assert 'var DATA_ID = "fy-doc-data";' in html


def test_payload_embeds_every_model_not_only_the_selected_one(parity_source):
    data = payload_of(flowyaml.render(parity_source, instance_id="fy-doc"))
    assert [model["id"] for model in data["models"]] == [
        "distribution",
        "procurement",
        "quotation",
        "dispatch",
    ]
    assert data["defaultModel"] == "distribution"
    assert data["hashKey"] == "model"
    assert data["output"] == "document"
    assert data["theme"] == "dornelles_multitech"
    assert data["layout"] == dict(LAYOUT_OPTIONS)


def test_model_id_selects_the_first_visible_level(parity_source):
    data = payload_of(
        flowyaml.render(parity_source, model_id="quotation", instance_id="fy-doc")
    )
    assert data["defaultModel"] == "quotation"
    assert len(data["models"]) == 4


def test_unknown_model_id_raises(parity_source):
    with pytest.raises(flowyaml.FlowYAMLModelError) as caught:
        flowyaml.render(parity_source, model_id="nope")
    assert "distribution" in str(caught.value)


def test_layout_uses_the_proven_elk_defaults():
    assert LAYOUT_OPTIONS["elk.algorithm"] == "layered"
    assert LAYOUT_OPTIONS["elk.direction"] == "RIGHT"
    assert LAYOUT_OPTIONS["elk.edgeRouting"] == "ORTHOGONAL"
    assert LAYOUT_OPTIONS["elk.layered.nodePlacement.strategy"] == "NETWORK_SIMPLEX"


def test_hostile_labels_never_break_out_of_the_payload(fixtures_dir):
    source = (fixtures_dir / "hostile_labels.yaml").read_text(encoding="utf-8")
    html = flowyaml.render(source, instance_id="fy-hostile")

    # Exactly the three script elements the renderer emits, and no injected one.
    assert len(re.findall(r"<script", html)) == 3
    assert len(re.findall(r"</script>", html)) == 3

    match = re.search(
        r'<script id="fy-hostile-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match
    embedded = match.group(1)
    # No angle bracket survives inside the payload, so no label can close the
    # element or start a new one.
    assert "<" not in embedded and ">" not in embedded

    # Outside the JSON payload, nothing from the source appears at all.
    outside = html.replace(embedded, "")
    assert "__flowyaml_pwned" not in outside
    assert "onerror" not in outside

    data = payload_of(html)
    labels = [node["label"] for node in data["models"][0]["nodes"]]
    # The value survives intact inside JSON, only its transport is escaped.
    assert "</script><script>window.__flowyaml_pwned = true;</script>" in labels


def test_payload_is_pure_ascii(fixtures_dir):
    source = (fixtures_dir / "hostile_labels.yaml").read_text(encoding="utf-8")
    html = flowyaml.render(source, instance_id="fy-ascii")
    match = re.search(
        r'<script id="fy-ascii-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match
    match.group(1).encode("ascii")  # raises if the payload depends on encoding


def test_instance_ids_differ_between_renders(minimal_source):
    first = flowyaml.render(minimal_source)
    second = flowyaml.render(minimal_source)
    ids = {
        re.search(r'<div id="(fy-[0-9a-f]+)"', html).group(1)
        for html in (first, second)
    }
    assert len(ids) == 2


def test_fixed_instance_id_makes_output_reproducible(minimal_source):
    first = flowyaml.render(minimal_source, instance_id="fy-fixed")
    second = flowyaml.render(minimal_source, instance_id="fy-fixed")
    assert first == second


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"output": "pdf"}, flowyaml.FlowYAMLOptionError),
        ({"assets": "url"}, flowyaml.FlowYAMLOptionError),
        ({"theme": "institutional_navy"}, flowyaml.FlowYAMLOptionError),
        ({"instance_id": "9bad id"}, flowyaml.FlowYAMLOptionError),
    ],
)
def test_unsupported_options_are_rejected(minimal_source, kwargs, error):
    with pytest.raises(error):
        flowyaml.render(minimal_source, **kwargs)


def test_dornelles_multitech_tokens_reach_the_stylesheet(minimal_source):
    html = flowyaml.render(minimal_source, instance_id="fy-theme")
    for token in ("#F7F5F1", "#151B24", "#202732", "#B46D3A", "#2F7D4E", "#B33A2E"):
        assert token in html
    # ERP DINFRA's institutional identity must not be inherited.
    assert "#0B2B54" not in html
    assert "navy" not in html.lower()


def test_theme_variables_are_scoped_to_the_instance(minimal_source):
    html = flowyaml.render(minimal_source, instance_id="fy-scope")
    assert "#fy-scope {\n  --fy-canvas: #F7F5F1;" in html


def test_render_file_and_write_html(tmp_path, parity_path):
    from_file = flowyaml.render_file(parity_path, instance_id="fy-file")
    assert from_file.startswith("<!doctype html>")

    target = tmp_path / "nested" / "out.html"
    written = flowyaml.write_html(parity_path, target, instance_id="fy-file")
    assert written == target
    assert target.read_text(encoding="utf-8") == from_file


def test_write_html_accepts_yaml_text_too(tmp_path, minimal_source):
    target = flowyaml.write_html(minimal_source, tmp_path / "text.html")
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_read_source_prefers_a_real_file_over_a_path_shaped_string(tmp_path):
    path = tmp_path / "flow.yaml"
    path.write_text("meta:\n  id: fromfile\n", encoding="utf-8")
    assert flowyaml.read_source(str(path)).startswith("meta:")
    assert flowyaml.read_source("meta:\n  id: inline\n").startswith("meta:")
    assert flowyaml.read_source("not-a-real.yaml") == "not-a-real.yaml"
