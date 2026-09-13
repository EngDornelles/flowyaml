"""Canonical YAML serialization, and the diagram-as-source public contract."""

from __future__ import annotations

import pytest

import flowyaml


def test_to_yaml_round_trips_a_hand_written_source(parity_source):
    diagram = flowyaml.load(parity_source)
    assert flowyaml.load(flowyaml.to_yaml(diagram)) == diagram


@pytest.mark.parametrize("fixture", ["kitchen_sink.mmd"])
def test_to_yaml_round_trips_an_imported_mermaid_flowchart(
    import_fixtures_dir, fixture
):
    diagram = flowyaml.read_mermaid(import_fixtures_dir / fixture)
    assert flowyaml.load(flowyaml.to_yaml(diagram)) == diagram


@pytest.mark.parametrize("fixture", ["order.bpmn", "two_pools.bpmn", "prefixes.xml"])
def test_to_yaml_round_trips_an_imported_bpmn_process(import_fixtures_dir, fixture):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / fixture)
    assert flowyaml.load(flowyaml.to_yaml(diagram)) == diagram


def test_to_yaml_accepts_yaml_text_too(minimal_source):
    assert flowyaml.load(flowyaml.to_yaml(minimal_source)) == flowyaml.load(
        minimal_source
    )


def test_yaml_booleans_are_quoted_back():
    """Regression: a bare Yes tag would come back as a boolean."""
    diagram = flowyaml.read_mermaid(
        "flowchart LR\n    g{Ready?} -->|Yes| a[Go]\n    g -->|No| b[Stop]\n"
    )
    text = flowyaml.to_yaml(diagram)
    assert "'Yes'" in text and "'No'" in text
    assert flowyaml.load(text).default_model.edges[0].tag == "Yes"


def test_the_examples_import_and_render(examples_dir):
    mermaid = flowyaml.read_mermaid(examples_dir / "onboarding.mmd")
    bpmn = flowyaml.read_bpmn(examples_dir / "order_handling.bpmn")
    for diagram in (mermaid, bpmn):
        assert flowyaml.validate(diagram) == ()
        assert flowyaml.render(diagram, instance_id="fy-ex").startswith("<!doctype")


def test_a_diagram_is_accepted_wherever_a_source_is(minimal_source, tmp_path):
    diagram = flowyaml.load(minimal_source)
    assert flowyaml.load(diagram) is diagram
    assert flowyaml.validate(diagram) == ()
    assert flowyaml.models(diagram) == ("minimal",)
    target = flowyaml.write_html(diagram, tmp_path / "out.html", instance_id="fy-d")
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_imported_yaml_carries_no_layout_keys(examples_dir):
    text = flowyaml.to_yaml(flowyaml.read_bpmn(examples_dir / "order_handling.bpmn"))
    for forbidden in ("ui:", "Bounds", "bpmndi", "  x:", "  y:"):
        assert forbidden not in text
