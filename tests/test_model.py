"""Normalization into the immutable graph model."""

from __future__ import annotations

import dataclasses
import textwrap

import pytest

import flowyaml


def test_documents_become_models_in_source_order(parity_source):
    diagram = flowyaml.load(parity_source)
    assert diagram.model_ids == ("distribution", "procurement", "quotation", "dispatch")
    assert diagram.default_model.id == "distribution"
    assert "quotation" in diagram
    assert diagram.get("nope") is None
    assert len(diagram) == 4


def test_models_helper_lists_ids(parity_path):
    assert flowyaml.models(parity_path) == (
        "distribution",
        "procurement",
        "quotation",
        "dispatch",
    )


def test_model_is_immutable(parity_source):
    model = flowyaml.load(parity_source).default_model
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.id = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.nodes[0].label = "changed"
    with pytest.raises(TypeError):
        model.meta["id"] = "changed"


def test_nested_metadata_is_frozen_too(parity_source):
    model = flowyaml.load(parity_source).default_model
    with pytest.raises(TypeError):
        model.extra["actors"][0]["name"] = "changed"


def test_labels_and_tags_are_normalized():
    source = textwrap.dedent(
        """
        meta:
          id: spacing
        nodes:
          - id: a
            type: task
            label: "  padded label  "
          - id: b
            type: task
            label: Second
        edges:
          - from: a
            to: b
            tag: "  two   words  "
            label: "  detailed   text  "
        """
    )
    model = flowyaml.load(source).default_model
    assert model.nodes[0].label == "padded label"
    # Tags become compact chips, so their whitespace collapses. Detailed
    # labels and node details reach a pre-wrap tooltip, so their internal
    # shape is preserved and only the outer padding is trimmed.
    assert model.edges[0].tag == "two words"
    assert model.edges[0].label == "detailed   text"


def test_edge_ids_are_stable_and_unique(parity_source):
    for model in flowyaml.load(parity_source):
        ids = [edge.id for edge in model.edges]
        assert len(ids) == len(set(ids))


def test_dotted_covers_both_kind_and_style(parity_source):
    dispatch = flowyaml.load(parity_source).get("dispatch")
    association = [edge for edge in dispatch.edges if edge.kind == "association"]
    assert association and all(edge.dotted for edge in association)

    distribution = flowyaml.load(parity_source).get("distribution")
    styled = [edge for edge in distribution.edges if edge.style == "dotted"]
    assert styled and all(edge.dotted for edge in styled)


def test_chip_prefers_the_tag_and_falls_back_to_a_shortened_label(parity_source):
    distribution = flowyaml.load(parity_source).get("distribution")
    by_pair = {(edge.source, edge.target): edge for edge in distribution.edges}

    tagged = by_pair[("stocked", "reserve")]
    assert tagged.chip == "In stock"
    assert tagged.tooltip.startswith("The requested quantity")

    untagged = by_pair[("archive_note", "end")]
    assert untagged.tag == ""
    assert untagged.chip.endswith("\u2026")
    assert len(untagged.chip) <= 28
    assert untagged.tooltip == untagged.label


def test_no_tooltip_when_the_chip_already_says_everything():
    source = textwrap.dedent(
        """
        meta:
          id: same
        nodes:
          - id: a
            type: task
            label: A
          - id: b
            type: task
            label: B
        edges:
          - from: a
            to: b
            tag: "Yes"
            label: "Yes"
        """
    )
    edge = flowyaml.load(source).default_model.edges[0]
    assert edge.chip == "Yes"
    assert edge.tooltip == ""


def test_bare_yes_is_reported_with_a_quoting_hint():
    source = textwrap.dedent(
        """
        meta:
          id: trap
        nodes:
          - id: a
            type: task
            label: A
          - id: b
            type: task
            label: B
        edges:
          - from: a
            to: b
            tag: Yes
        """
    )
    issue = flowyaml.validate(source)[0]
    assert issue.code == "edge.tag.invalid"
    assert "YAML booleans" in issue.message


def test_detail_and_description_are_both_accepted():
    source = textwrap.dedent(
        """
        meta:
          id: details
        nodes:
          - id: a
            type: state
            label: Held
            detail: The detail field.
          - id: b
            type: state
            label: Also held
            description: The description field.
        edges: []
        """
    )
    model = flowyaml.load(source).default_model
    assert model.node("a").detail == "The detail field."
    assert model.node("b").detail == "The description field."


def test_payload_only_carries_render_relevant_keys(parity_source):
    model = flowyaml.load(parity_source).default_model
    payload = model.to_payload()
    assert set(payload) >= {"id", "name", "title", "nodes", "edges", "version"}
    assert "actors" not in payload
    node = next(item for item in payload["nodes"] if item["id"] == "procurement")
    assert node["ref"] == "procurement"
    assert "detail" in node
    plain = next(item for item in payload["nodes"] if item["id"] == "register")
    assert "ref" not in plain and "detail" not in plain


def test_subprocess_flag_and_title_fallback():
    source = "meta:\n  id: only\nnodes:\n  - id: s\n    type: subprocess\n    label: S\nedges: []\n"
    model = flowyaml.load(source).default_model
    assert model.title == "only"
    assert model.node("s").is_subprocess
