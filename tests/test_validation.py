"""Every validation rule the v0 specification states."""

from __future__ import annotations

import textwrap

import pytest

import flowyaml
from flowyaml.validation import build

VALID = textwrap.dedent(
    """
    meta:
      id: base
      name: Base
      version: "1.0.0"
    nodes:
      - id: start
        type: startEvent
        label: Open
      - id: end
        type: endEvent
        label: Close
    edges:
      - from: start
        to: end
    """
)


#: The one labelled node in VALID, as it appears in the source text.
LABELLED_START = "type: startEvent" + chr(10) + "    label: Open"


def codes(source: str) -> list[str]:
    return [issue.code for issue in flowyaml.validate(source)]


def test_a_valid_source_reports_nothing():
    assert flowyaml.validate(VALID) == ()


def test_render_raises_when_issues_exist():
    with pytest.raises(flowyaml.FlowYAMLValidationError) as caught:
        flowyaml.render("meta:\n  name: no id\nnodes: []\nedges: []\n")
    assert caught.value.issues
    assert "meta.id.missing" in str(caught.value)


def test_empty_source_is_rejected():
    assert codes("") == ["source.empty"]
    assert codes("# only a comment\n") == ["source.empty"]


def test_document_must_be_a_mapping():
    assert codes("- just\n- a list\n") == ["document.not_mapping"]


def test_meta_rules():
    assert codes("nodes: []\nedges: []\n") == ["meta.missing"]
    assert codes("meta: not-a-mapping\nnodes: []\nedges: []\n") == ["meta.not_mapping"]
    assert codes("meta:\n  name: x\nnodes: []\nedges: []\n") == ["meta.id.missing"]
    assert codes("meta:\n  id: 7\nnodes: []\nedges: []\n") == ["meta.id.invalid"]


def test_model_ids_are_unique_across_documents():
    assert codes(VALID + "\n---\n" + VALID) == ["meta.id.duplicate"]


def test_nodes_rules():
    assert codes("meta:\n  id: a\nedges: []\n") == ["nodes.missing"]
    assert codes("meta:\n  id: a\nnodes: {}\nedges: []\n") == ["nodes.not_list"]
    assert codes("meta:\n  id: a\nnodes: []\nedges: []\n") == ["nodes.empty"]


def test_edges_key_is_required_but_may_be_empty(fixtures_dir):
    source = (fixtures_dir / "no_edges.yaml").read_text(encoding="utf-8")
    assert flowyaml.validate(source) == ()
    assert codes(
        "meta:\n  id: a\nnodes:\n  - id: n\n    type: task\n    label: L\n"
    ) == ["edges.missing"]


def test_node_ids_are_unique_in_their_model():
    source = textwrap.dedent(
        """
        meta:
          id: dupes
        nodes:
          - id: same
            type: task
            label: One
          - id: same
            type: task
            label: Two
        edges: []
        """
    )
    assert codes(source) == ["node.id.duplicate"]


def test_node_type_must_be_supported():
    source = VALID.replace("type: startEvent", "type: swimlane")
    issues = flowyaml.validate(source)
    assert [issue.code for issue in issues] == ["node.type.unsupported"]
    assert issues[0].field == "nodes[0].type"
    assert issues[0].model_id == "base"
    assert issues[0].line is not None


@pytest.mark.parametrize("node_type", flowyaml.NODE_TYPES)
def test_every_documented_node_type_is_accepted(node_type):
    source = textwrap.dedent(
        f"""
        meta:
          id: types
        nodes:
          - id: probe
            type: {node_type}
            label: Probe
          - id: other
            type: task
            label: Other
        edges:
          - from: probe
            to: other
        """
    )
    assert flowyaml.validate(source) == ()


def test_labels_may_be_empty_only_for_gateways(fixtures_dir):
    merge = (fixtures_dir / "merge_gateway.yaml").read_text(encoding="utf-8")
    assert flowyaml.validate(merge) == ()
    assert codes(VALID.replace("label: Open", 'label: ""')) == ["node.label.empty"]


def test_an_unlabelled_intermediate_event_is_a_connector_not_an_error(fixtures_dir):
    """Regression: the ERP DINFRA source uses one as a plain junction.

    Acceptance criterion 1 requires that source to validate unmutated, and it
    carries ``{id: e_dist, type: intermediateEvent, label: ""}``. Rejecting it
    also made every subprocess pointing at its document look unresolved.
    """
    source = (fixtures_dir / "connector_junction.yaml").read_text(encoding="utf-8")
    assert flowyaml.validate(source) == ()
    model = flowyaml.load(source).default_model
    assert model.node("junction").label == ""
    assert model.node("merge").label == ""


@pytest.mark.parametrize(
    "node_type", ["task", "state", "subprocess", "startEvent", "endEvent"]
)
def test_only_connector_shapes_may_drop_their_label(node_type):
    """Every type that carries process meaning still needs text."""
    source = VALID.replace(
        LABELLED_START,
        LABELLED_START.replace("startEvent", node_type).replace("Open", '""'),
    )
    assert codes(source) == ["node.label.empty"]


def test_edge_endpoints_must_resolve():
    assert codes(VALID.replace("from: start", "from: ghost")) == ["edge.from.unresolved"]
    assert codes(VALID.replace("to: end", "to: ghost")) == ["edge.to.unresolved"]
    assert codes(VALID.replace("- from: start", "- from: end")) == ["edge.self_loop"]


EDGE_BLOCK = "  - from: start\n    to: end\n"


def test_edge_needs_both_endpoints():
    assert codes(VALID.replace(EDGE_BLOCK, "  - to: end\n")) == ["edge.from.missing"]
    assert codes(VALID.replace(EDGE_BLOCK, "  - from: start\n")) == ["edge.to.missing"]


def test_a_broken_node_does_not_cascade_into_its_edges():
    """One root cause reports one issue, not one issue per touching edge."""
    issues = flowyaml.validate(VALID.replace("type: startEvent", "type: swimlane"))
    assert [issue.code for issue in issues] == ["node.type.unsupported"]


def test_unsupported_edge_kind_and_style_are_rejected():
    assert codes(VALID.replace(EDGE_BLOCK, EDGE_BLOCK + "    kind: dependency\n")) == [
        "edge.kind.unsupported"
    ]
    assert codes(VALID.replace(EDGE_BLOCK, EDGE_BLOCK + "    style: wavy\n")) == [
        "edge.style.unsupported"
    ]


def test_association_and_dotted_are_accepted():
    assert flowyaml.validate(VALID.replace(EDGE_BLOCK, EDGE_BLOCK + "    kind: association\n")) == ()
    assert flowyaml.validate(VALID.replace(EDGE_BLOCK, EDGE_BLOCK + "    style: dotted\n")) == ()


NODE_BLOCK = "  - id: end\n    type: endEvent\n    label: Close\n"


def test_subprocess_ref_must_resolve_to_an_embedded_model():
    source = VALID.replace(
        NODE_BLOCK,
        NODE_BLOCK + "  - id: sub\n    type: subprocess\n    label: Sub\n    ref: nowhere\n",
    )
    issues = flowyaml.validate(source)
    assert [issue.code for issue in issues] == ["node.ref.unresolved"]
    assert issues[0].field == "nodes[2].ref"
    assert issues[0].model_id == "base"


def test_a_broken_document_does_not_orphan_the_refs_pointing_at_it():
    """Regression: one root cause reports one issue, across documents too.

    ``spc`` fails on its own node, but the parent's subprocess reference to
    it is still satisfiable, so it must not also be reported as unresolved.
    """
    source = textwrap.dedent(
        """
        meta:
          id: top
        nodes:
          - id: sub
            type: subprocess
            label: Section
            ref: spc
        edges: []
        ---
        meta:
          id: spc
        nodes:
          - id: broken
            type: swimlane
            label: Not a v0 type
        edges: []
        """
    )
    assert codes(source) == ["node.type.unsupported"]


def test_a_duplicate_model_id_is_caught_even_when_the_first_document_failed():
    """The id table records declarations, not only successful builds."""
    document = textwrap.dedent(
        """
        meta:
          id: same
        nodes:
          - id: broken
            type: swimlane
            label: Not a v0 type
        edges: []
        """
    )
    source = document + "---" + chr(10) + document
    assert codes(source) == ["node.type.unsupported", "meta.id.duplicate"]


def test_subprocess_without_a_ref_is_valid():
    source = VALID.replace(
        NODE_BLOCK,
        NODE_BLOCK + "  - id: sub\n    type: subprocess\n    label: External step\n",
    )
    assert flowyaml.validate(source) == ()


def test_only_subprocess_nodes_may_carry_a_ref():
    assert codes(VALID.replace("    label: Open\n", "    label: Open\n    ref: base\n")) == [
        "node.ref.unsupported"
    ]


def test_unknown_metadata_is_preserved_not_rejected():
    source = VALID + "actors:\n  - id: unit\n    name: Requesting unit\n"
    assert flowyaml.validate(source) == ()
    model = flowyaml.load(source).default_model
    assert model.extra["actors"][0]["name"] == "Requesting unit"


def test_issue_str_carries_code_location_and_message():
    issue = flowyaml.validate(VALID.replace("type: startEvent", "type: swimlane"))[0]
    rendered = str(issue)
    assert "node.type.unsupported" in rendered
    assert "model 'base'" in rendered
    assert "nodes[0].type" in rendered
    assert "line" in rendered


def test_build_returns_no_diagram_when_issues_exist():
    diagram, issues = build("meta:\n  id: x\nnodes: []\nedges: []\n")
    assert diagram is None
    assert issues


def test_parity_example_is_valid(parity_source):
    assert flowyaml.validate(parity_source) == ()
