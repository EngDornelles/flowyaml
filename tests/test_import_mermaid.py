"""Mermaid flowchart import: mapping, labels, structure and refusals."""

from __future__ import annotations

import textwrap

import pytest

import flowyaml
from flowyaml.errors import FlowYAMLImportError

SIMPLE = textwrap.dedent(
    """
    flowchart TD
        a([Start]) --> b[Do the work]
        b --> c((Done))
    """
)


def load(source: str, **options) -> flowyaml.Diagram:
    return flowyaml.read_mermaid(source, **options)


def only(source: str, **options) -> flowyaml.Model:
    return load(source, **options).default_model


def types(model: flowyaml.Model) -> dict[str, str]:
    return {node.id: node.type for node in model.nodes}


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_text_becomes_one_validated_model():
    diagram = load(SIMPLE)
    assert isinstance(diagram, flowyaml.Diagram)
    assert flowyaml.validate(diagram) == ()
    assert diagram.model_ids == ("flowchart",)
    model = diagram.default_model
    assert [node.id for node in model.nodes] == ["a", "b", "c"]
    assert [(edge.source, edge.target) for edge in model.edges] == [
        ("a", "b"),
        ("b", "c"),
    ]


def test_a_path_is_read_and_names_the_model(import_fixtures_dir):
    diagram = flowyaml.read_mermaid(import_fixtures_dir / "kitchen_sink.mmd")
    assert diagram.model_ids == ("kitchen_sink",)
    assert diagram.default_model.name == "Kitchen sink"


def test_a_bare_string_path_is_read_too(import_fixtures_dir):
    diagram = flowyaml.read_mermaid(str(import_fixtures_dir / "kitchen_sink.mmd"))
    assert diagram.model_ids == ("kitchen_sink",)


def test_the_result_renders_without_a_yaml_round_trip():
    html = flowyaml.render(load(SIMPLE), instance_id="fy-mermaid")
    assert html.startswith("<!doctype html>")
    assert "Do the work" in html


def test_ids_and_labels_survive_the_import():
    model = only(
        "graph LR\n    check_stock[Check stock availability] --> done([Closed])\n"
    )
    assert model.node("check_stock").label == "Check stock availability"
    assert model.node("done").label == "Closed"


def test_an_undeclared_node_falls_back_to_its_own_id():
    model = only("graph LR\n    alpha --> beta\n")
    assert model.node("alpha").label == "alpha"
    assert model.node("beta").label == "beta"


def test_model_id_and_name_can_be_supplied():
    model = only(SIMPLE, model_id="intake", name="Intake flow")
    assert model.id == "intake"
    assert model.name == "Intake flow"


def test_declared_direction_is_kept_as_provenance():
    assert only(SIMPLE).meta["source_direction"] == "TD"
    assert only(SIMPLE).meta["source_format"] == "mermaid"
    assert "source_direction" not in only("graph\n    a --> b\n").meta


def test_no_layout_metadata_is_ever_emitted():
    model = only(SIMPLE)
    forbidden = {"ui", "x", "y", "width", "height", "position", "layout"}
    assert not forbidden & set(model.meta)
    assert not forbidden & set(model.extra)
    for node in model.nodes:
        assert not forbidden & set(node.extra)
    for edge in model.edges:
        assert not forbidden & set(edge.extra)


# --------------------------------------------------------------------------- #
# shapes and node types
# --------------------------------------------------------------------------- #


SHAPE_CASES = [
    ("n[Plain]", "task"),
    ("n(Rounded)", "task"),
    ("n[[Subroutine]]", "subprocess"),
    ("n[(Database)]", "state"),
    ("n[/Parallelogram/]", "state"),
    (r"n[\Reverse\]", "state"),
    (r"n[/Trapezoid\]", "state"),
    (r"n[\Trapezoid alt/]", "state"),
    ("n{Rhombus}", "gateway"),
    ("n{{Hexagon}}", "gateway"),
    ("n>Asymmetric]", "intermediateEvent"),
    ("n(((Double circle)))", "endEvent"),
]


@pytest.mark.parametrize("declaration,expected", SHAPE_CASES)
def test_every_supported_shape_maps_to_one_node_type(declaration, expected):
    model = only(f"flowchart LR\n    head --> {declaration} --> tail\n")
    assert types(model)["n"] == expected


@pytest.mark.parametrize("shape", ["([Event])", "((Event))"])
def test_a_circle_or_stadium_takes_its_role_from_the_graph(shape):
    source = f"flowchart LR\n    n{shape} --> b[Work]\n"
    assert types(only(source))["n"] == "startEvent"

    source = f"flowchart LR\n    b[Work] --> n{shape}\n"
    assert types(only(source))["n"] == "endEvent"

    source = f"flowchart LR\n    a[In] --> n{shape} --> b[Out]\n"
    assert types(only(source))["n"] == "intermediateEvent"


def test_the_first_explicit_shape_wins():
    model = only(
        "flowchart LR\n    a[First label] --> b[Other]\n    a[Second label] --> b\n"
    )
    assert model.node("a").label == "First label"


def test_a_bare_reference_never_erases_a_later_declaration():
    model = only("flowchart LR\n    a --> b\n    b{Decision?}\n")
    assert types(model)["b"] == "gateway"
    assert model.node("b").label == "Decision?"


def test_an_empty_gateway_label_is_allowed():
    model = only("flowchart LR\n    a[In] --> m{ } --> b[Out]\n")
    assert model.node("m").type == "gateway"
    assert model.node("m").label == ""


# --------------------------------------------------------------------------- #
# labels
# --------------------------------------------------------------------------- #


def test_quoted_labels_carry_reserved_characters():
    model = only('flowchart LR\n    a["Stock [reserved] & held"] --> b[Next]\n')
    assert model.node("a").label == "Stock [reserved] & held"


def test_line_breaks_and_entities_are_decoded():
    model = only(
        'flowchart LR\n    a["First line<br/>Second #quot;quoted#quot;"] --> b[x]\n'
    )
    assert model.node("a").label == 'First line\nSecond "quoted"'


def test_html_entities_are_decoded_too():
    model = only("flowchart LR\n    a[Ledger &amp; audit] --> b[x]\n")
    assert model.node("a").label == "Ledger & audit"


def test_accented_labels_survive():
    model = only("flowchart LR\n    a[Distribuição de material] --> b[Fim]\n")
    assert model.node("a").label == "Distribuição de material"


# --------------------------------------------------------------------------- #
# links
# --------------------------------------------------------------------------- #


def test_short_edge_text_becomes_a_chip_and_long_text_becomes_a_tooltip():
    model = only(
        "flowchart LR\n"
        "    g{Ready?} -->|Yes| a[Go]\n"
        "    g -->|The documentation is complete and filed| b[Wait]\n"
    )
    short, long = model.edges
    assert (short.tag, short.label) == ("Yes", "")
    assert short.chip == "Yes"
    assert long.tag == ""
    assert long.label == "The documentation is complete and filed"
    assert long.tooltip == long.label


@pytest.mark.parametrize(
    "link,text",
    [
        ("-->|Yes|", "Yes"),
        ("-- Yes -->", "Yes"),
        ("-- Yes ---", "Yes"),
        ("== Yes ==>", "Yes"),
        ("==>|Yes|", "Yes"),
        ("-. Yes .->", "Yes"),
        ("-.->|Yes|", "Yes"),
    ],
)
def test_every_labelled_link_spelling_reads_the_same_text(link, text):
    model = only(f"flowchart LR\n    a[In] {link} b[Out]\n")
    assert model.edges[0].tag == text


@pytest.mark.parametrize("link", ["-->", "---", "--->", "--o", "--x", "==>", "===", "<-->"])
def test_solid_links_stay_sequence_edges(link):
    edge = only(f"flowchart LR\n    a[In] {link} b[Out]\n").edges[0]
    assert (edge.kind, edge.style) == ("sequence", "solid")
    assert edge.dotted is False


@pytest.mark.parametrize("link", ["-.->", "-.-", "-..->", "~~~", "-. why .->"])
def test_dotted_and_invisible_links_become_dotted_associations(link):
    edge = only(f"flowchart LR\n    a[In] {link} b[Out]\n").edges[0]
    assert (edge.kind, edge.style) == ("association", "dotted")
    assert edge.dotted is True


def test_a_plain_chain_is_not_read_as_a_labelled_link():
    """Regression: "A --- B --- C" is a chain, not one link labelled "B"."""
    model = only("flowchart LR\n    a[A] --- b[B] --- c[C]\n")
    assert [(edge.source, edge.target) for edge in model.edges] == [
        ("a", "b"),
        ("b", "c"),
    ]
    assert [edge.tag for edge in model.edges] == ["", ""]


def test_chains_and_ampersand_groups_expand_to_every_pair():
    model = only("flowchart LR\n    a[A] & b[B] --> c[C] & d[D]\n")
    assert {(edge.source, edge.target) for edge in model.edges} == {
        ("a", "c"),
        ("a", "d"),
        ("b", "c"),
        ("b", "d"),
    }


def test_statements_split_on_semicolons():
    model = only("graph TD;a[A]-->b[B];b-->c[C];")
    assert len(model.nodes) == 3
    assert len(model.edges) == 2


def test_edge_ids_stay_unique():
    model = only("flowchart LR\n    a[A] --> b[B]\n    a --> b\n")
    assert len({edge.id for edge in model.edges}) == 2


# --------------------------------------------------------------------------- #
# statements v0 reads past
# --------------------------------------------------------------------------- #


def test_comments_directives_and_styling_are_discarded():
    model = only(
        textwrap.dedent(
            """
            %%{init: {"theme": "dark"}}%%
            %% a plain comment
            flowchart LR
                a[A]:::warm --> b[B]
                classDef warm fill:#f00
                class a warm
                style b stroke:#000
                linkStyle 0 stroke:#333
                click a "https://example.invalid"
            """
        )
    )
    assert [node.id for node in model.nodes] == ["a", "b"]
    assert model.node("a").label == "A"


def test_frontmatter_supplies_the_model_name():
    model = only("---\ntitle: Supplier onboarding\n---\nflowchart LR\n  a[A]-->b[B]\n")
    assert model.name == "Supplier onboarding"


def test_an_explicit_name_beats_the_frontmatter_title():
    model = only(
        "---\ntitle: Ignored\n---\nflowchart LR\n  a[A]-->b[B]\n", name="Chosen"
    )
    assert model.name == "Chosen"


# --------------------------------------------------------------------------- #
# subgraphs
# --------------------------------------------------------------------------- #


def test_a_subgraph_flattens_but_keeps_its_membership():
    model = only(
        textwrap.dedent(
            """
            flowchart LR
                a[Outside] --> b[Inside]
                subgraph zone [Restricted zone]
                    b --> c[Also inside]
                end
                c --> d[Outside again]
            """
        )
    )
    assert [node.id for node in model.nodes] == ["a", "b", "c", "d"]
    assert model.node("b").extra.get("group") is None
    assert model.node("c").extra["group"] == "zone"
    assert model.extra["groups"] == ({"id": "zone", "title": "Restricted zone"},)


def test_a_bare_subgraph_title_still_produces_a_group():
    model = only(
        "flowchart LR\n  subgraph Packaging area\n    a[A] --> b[B]\n  end\n"
    )
    assert model.extra["groups"][0]["title"] == "Packaging area"


def test_nested_subgraphs_take_the_innermost_membership():
    model = only(
        textwrap.dedent(
            """
            flowchart LR
                subgraph outer [Outer]
                    subgraph inner [Inner]
                        a[A] --> b[B]
                    end
                    b --> c[C]
                end
            """
        )
    )
    assert model.node("a").extra["group"] == "inner"
    assert model.node("c").extra["group"] == "outer"
    assert len(model.extra["groups"]) == 2


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #


def caught(source: str, **options) -> FlowYAMLImportError:
    with pytest.raises(FlowYAMLImportError) as error:
        flowyaml.read_mermaid(source, **options)
    return error.value


def test_an_import_error_is_a_flowyaml_error():
    assert issubclass(FlowYAMLImportError, flowyaml.FlowYAMLError)
    error = caught("sequenceDiagram\n    A->>B: hello\n")
    assert error.source_format == "mermaid"
    assert "sequenceDiagram is not a flowchart" in str(error)


def test_a_missing_header_is_refused_with_what_it_found():
    error = caught("a[A] --> b[B]\n")
    assert "expected a 'graph' or 'flowchart' declaration" in str(error)
    assert error.line == 1


def test_an_empty_source_is_refused():
    assert "no Mermaid statement" in str(caught("%% nothing but a comment\n"))


def test_a_flowchart_without_a_node_is_refused():
    assert "declares no node" in str(caught("flowchart LR\n"))


def test_an_unclosed_shape_names_its_delimiter():
    error = caught("flowchart LR\n    a[Unfinished --> b\n")
    assert "is never closed" in str(error)
    assert error.line == 2


def test_an_unclosed_edge_text_is_refused():
    assert "never closed" in str(caught("flowchart LR\n    a[A] -->|open b[B]\n"))


def test_a_self_loop_is_refused_by_name():
    error = caught("flowchart LR\n    a[A] --> a\n")
    assert "self-loop on node 'a'" in str(error)


def test_a_subgraph_cannot_be_an_edge_endpoint():
    error = caught(
        "flowchart LR\n  subgraph zone [Zone]\n    a[A] --> b[B]\n  end\n  zone --> c[C]\n"
    )
    assert "cannot be an edge endpoint" in str(error)


def test_an_unbalanced_subgraph_is_refused():
    assert "never closed with 'end'" in str(
        caught("flowchart LR\n  subgraph zone [Zone]\n    a[A] --> b[B]\n")
    )
    assert "without an open subgraph" in str(caught("flowchart LR\n  a[A]\n  end\n"))


def test_the_extended_shape_syntax_is_refused_explicitly():
    error = caught('flowchart LR\n    a@{ shape: rect, label: "x" } --> b[B]\n')
    assert "'@{ shape: ... }' node syntax is not supported" in str(error)


def test_a_missing_file_is_a_clean_import_error(tmp_path):
    error = caught(str(tmp_path / "absent.mmd"))
    assert "looks like a path but no such file exists" in str(error)


def test_a_non_string_source_is_a_type_error():
    with pytest.raises(TypeError):
        flowyaml.read_mermaid(42)  # type: ignore[arg-type]
