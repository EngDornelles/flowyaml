"""BPMN 2.0 XML import: mapping, nesting, artifacts and refusals."""

from __future__ import annotations

import textwrap

import pytest

import flowyaml
from flowyaml.errors import FlowYAMLImportError

NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'


def definitions(body: str, *, process_attrs: str = 'id="P" name="Process"') -> str:
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <bpmn:definitions {NS} id="D">
          <bpmn:process {process_attrs}>
        {textwrap.indent(textwrap.dedent(body).strip(), "    ")}
          </bpmn:process>
        </bpmn:definitions>
        """
    )


def only(body: str, **options) -> flowyaml.Model:
    return flowyaml.read_bpmn(definitions(body), **options).default_model


def types(model: flowyaml.Model) -> dict[str, str]:
    return {node.id: node.type for node in model.nodes}


LINEAR = """
<bpmn:startEvent id="s" name="Open"/>
<bpmn:userTask id="t" name="Do the work"/>
<bpmn:endEvent id="e" name="Close"/>
<bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t"/>
<bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e"/>
"""


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_a_process_becomes_one_validated_model():
    diagram = flowyaml.read_bpmn(definitions(LINEAR))
    assert flowyaml.validate(diagram) == ()
    assert diagram.model_ids == ("P",)
    model = diagram.default_model
    assert model.name == "Process"
    assert [node.id for node in model.nodes] == ["s", "t", "e"]
    assert [(edge.source, edge.target) for edge in model.edges] == [("s", "t"), ("t", "e")]


def test_a_path_is_read(import_fixtures_dir):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn")
    assert diagram.model_ids == ("Process_order", "SubProcess_procure")


def test_the_result_renders_without_a_yaml_round_trip():
    html = flowyaml.render(flowyaml.read_bpmn(definitions(LINEAR)), instance_id="fy-bpmn")
    assert html.startswith("<!doctype html>")
    assert "Do the work" in html


def test_bpmn_ids_and_names_are_preserved():
    model = only(LINEAR)
    assert model.node("t").label == "Do the work"
    assert model.node("t").extra["bpmn"] == "userTask"


def test_meta_records_the_source_notation():
    model = only(LINEAR)
    assert model.meta["source_format"] == "bpmn"
    assert model.meta["source_element"] == "process"


def test_model_id_and_name_can_be_supplied():
    model = only(LINEAR, model_id="intake", name="Intake")
    assert (model.id, model.name) == ("intake", "Intake")


@pytest.mark.parametrize("fixture", ["prefixes.xml", "two_pools.bpmn", "order.bpmn"])
def test_every_namespace_prefix_reads_the_same(import_fixtures_dir, fixture):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / fixture)
    assert flowyaml.validate(diagram) == ()
    assert diagram.models


# --------------------------------------------------------------------------- #
# element type mapping
# --------------------------------------------------------------------------- #


TYPE_CASES = [
    ("startEvent", "startEvent"),
    ("endEvent", "endEvent"),
    ("intermediateCatchEvent", "intermediateEvent"),
    ("intermediateThrowEvent", "intermediateEvent"),
    ("task", "task"),
    ("userTask", "task"),
    ("serviceTask", "task"),
    ("scriptTask", "task"),
    ("manualTask", "task"),
    ("businessRuleTask", "task"),
    ("sendTask", "task"),
    ("receiveTask", "task"),
    ("callActivity", "subprocess"),
    ("exclusiveGateway", "gateway"),
    ("inclusiveGateway", "gateway"),
    ("parallelGateway", "gateway"),
    ("eventBasedGateway", "gateway"),
    ("complexGateway", "gateway"),
    ("dataObjectReference", "state"),
    ("dataStoreReference", "state"),
]


@pytest.mark.parametrize("element,expected", TYPE_CASES)
def test_every_supported_element_maps_to_one_node_type(element, expected):
    model = only(
        f'<bpmn:startEvent id="s" name="Open"/>\n'
        f'<bpmn:{element} id="n" name="Subject"/>\n'
        f'<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="n"/>\n'
    )
    assert types(model)["n"] == expected
    assert model.node("n").extra["bpmn"] == element


def test_a_collapsed_subprocess_is_a_destination_card():
    model = only(
        '<bpmn:startEvent id="s" name="Open"/>\n'
        '<bpmn:subProcess id="sub" name="Collapsed"/>\n'
        '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="sub"/>\n'
    )
    assert model.node("sub").type == "subprocess"
    assert model.node("sub").ref is None


def test_a_text_annotation_carries_its_own_text():
    model = only(
        '<bpmn:startEvent id="s" name="Open"/>\n'
        '<bpmn:endEvent id="e" name="Close"/>\n'
        '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="e"/>\n'
        '<bpmn:textAnnotation id="a"><bpmn:text>Escalate after a week.</bpmn:text></bpmn:textAnnotation>\n'
        '<bpmn:association id="as" sourceRef="a" targetRef="e"/>\n'
    )
    annotation = model.node("a")
    assert (annotation.type, annotation.label) == ("state", "Escalate after a week.")
    edge = model.edges[-1]
    assert (edge.kind, edge.style, edge.dotted) == ("association", "dotted", True)


def test_documentation_becomes_the_detail_tooltip():
    model = only(
        '<bpmn:startEvent id="s" name="Open">'
        "<bpmn:documentation>From the approved queue.</bpmn:documentation>"
        "</bpmn:startEvent>\n"
        '<bpmn:endEvent id="e" name="Close"/>\n'
        '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="e"/>\n'
    )
    assert model.node("s").detail == "From the approved queue."


def test_an_unnamed_connector_keeps_an_empty_label():
    model = only(
        '<bpmn:startEvent id="s" name="Open"/>\n'
        '<bpmn:parallelGateway id="g"/>\n'
        '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="g"/>\n'
    )
    assert model.node("g").label == ""


def test_an_unnamed_task_falls_back_to_its_bpmn_id():
    model = only(
        '<bpmn:startEvent id="s" name="Open"/>\n'
        '<bpmn:task id="Activity_0x9f2c"/>\n'
        '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="Activity_0x9f2c"/>\n'
    )
    assert model.node("Activity_0x9f2c").label == "Activity_0x9f2c"


# --------------------------------------------------------------------------- #
# structure: levels, flows and artifacts
# --------------------------------------------------------------------------- #


def test_an_expanded_subprocess_becomes_its_own_level(import_fixtures_dir):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn")
    parent, child = diagram.models
    card = parent.node("SubProcess_procure")
    assert card.type == "subprocess"
    assert card.ref == child.id
    assert child.meta["source_element"] == "subProcess"
    assert [node.id for node in child.nodes] == ["SubStart_1", "SubTask_quote", "SubEnd_1"]


def test_a_call_activity_references_the_process_it_calls(import_fixtures_dir):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "two_pools.bpmn")
    assert diagram.model_ids == ("Process_a", "Process_b")
    assert diagram.get("Process_a").node("a_call").ref == "Process_b"


def test_a_participant_name_titles_its_process(import_fixtures_dir):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "two_pools.bpmn")
    assert diagram.get("Process_a").name == "Requesting unit"


def test_an_empty_pool_produces_no_level(import_fixtures_dir):
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "two_pools.bpmn")
    assert "Process_empty" not in diagram.model_ids


def test_a_message_flow_across_pools_is_dropped(import_fixtures_dir):
    """It decorates a collaboration, and v0 renders one level at a time."""
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "two_pools.bpmn")
    for model in diagram:
        assert all(edge.kind == "sequence" for edge in model.edges)


def test_lanes_become_actors_and_node_provenance(import_fixtures_dir):
    model = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn").default_model
    assert model.extra["actors"] == (
        {"id": "Lane_desk", "name": "Front desk"},
        {"id": "Lane_supply", "name": "Supply"},
    )
    assert model.node("StartEvent_1").extra["lane"] == "Front desk"
    assert "lane" not in model.node("Task_reserve").extra


def test_a_boundary_event_is_associated_with_its_activity(import_fixtures_dir):
    model = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn").default_model
    attached = [
        edge
        for edge in model.edges
        if (edge.source, edge.target) == ("Task_reserve", "Boundary_timer")
    ]
    assert len(attached) == 1
    assert attached[0].dotted is True


def test_a_data_association_reaches_the_activity_it_feeds(import_fixtures_dir):
    model = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn").default_model
    fed = [
        edge
        for edge in model.edges
        if (edge.source, edge.target) == ("DataObjectReference_form", "Task_register")
    ]
    assert len(fed) == 1
    assert fed[0].kind == "association"


def test_a_short_flow_name_becomes_a_chip_and_a_long_one_a_tooltip():
    model = only(
        '<bpmn:exclusiveGateway id="g" name="Ready?"/>\n'
        '<bpmn:task id="a" name="Go"/>\n'
        '<bpmn:task id="b" name="Wait"/>\n'
        '<bpmn:sequenceFlow id="f1" name="Yes" sourceRef="g" targetRef="a"/>\n'
        '<bpmn:sequenceFlow id="f2" name="The documentation is complete and filed"'
        ' sourceRef="g" targetRef="b"/>\n'
    )
    short, long = model.edges
    assert (short.tag, short.label) == ("Yes", "")
    assert (long.tag, long.label) == ("", "The documentation is complete and filed")


def test_diagram_interchange_is_read_past(import_fixtures_dir):
    """The bpmndi half is geometry, and FlowYAML lays out in the browser."""
    diagram = flowyaml.read_bpmn(import_fixtures_dir / "order.bpmn")
    forbidden = {"ui", "x", "y", "width", "height", "bounds", "position", "layout"}
    for model in diagram:
        assert not forbidden & set(model.meta)
        assert not forbidden & set(model.extra)
        for node in model.nodes:
            assert not forbidden & set(node.extra)
        for edge in model.edges:
            assert not forbidden & set(edge.extra)
    assert "BPMNShape" not in flowyaml.to_yaml(diagram)


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #


def caught(source: str, **options) -> FlowYAMLImportError:
    with pytest.raises(FlowYAMLImportError) as error:
        flowyaml.read_bpmn(source, **options)
    return error.value


def test_malformed_xml_reports_its_position():
    error = caught(f'<bpmn:definitions {NS}><bpmn:process id="P">')
    assert "not well formed XML" in str(error)
    assert error.source_format == "bpmn"
    assert error.line == 1


def test_a_non_bpmn_root_is_refused():
    assert "not 'definitions'" in str(caught("<svg><g/></svg>"))


def test_a_definitions_without_a_process_is_refused():
    assert "declares no process" in str(caught(f"<bpmn:definitions {NS}/>"))


def test_a_process_without_a_flow_node_is_refused():
    error = caught(
        f'<bpmn:definitions {NS}><bpmn:process id="P"/></bpmn:definitions>'
    )
    assert "no process in this file declares a flow node" in str(error)


def test_an_unsupported_flow_element_is_named_not_dropped():
    error = caught(
        definitions(
            '<bpmn:startEvent id="s" name="Open"/>\n'
            '<bpmn:choreographyTask id="c" name="Chat"/>\n'
        )
    )
    assert "choreographyTask" in str(error)
    assert "not supported by FlowYAML v0" in str(error)


def test_an_unresolved_sequence_flow_is_refused():
    error = caught(
        definitions(
            '<bpmn:startEvent id="s" name="Open"/>\n'
            '<bpmn:endEvent id="e" name="Close"/>\n'
            '<bpmn:sequenceFlow id="f" sourceRef="s" targetRef="ghost"/>\n'
        )
    )
    assert "references 'ghost'" in str(error)


def test_a_sequence_flow_without_ends_is_refused():
    error = caught(
        definitions(
            '<bpmn:startEvent id="s" name="Open"/>\n'
            '<bpmn:sequenceFlow id="f" sourceRef="s"/>\n'
        )
    )
    assert "missing 'sourceRef' or 'targetRef'" in str(error)


def test_a_self_loop_is_refused():
    error = caught(
        definitions(
            '<bpmn:task id="t" name="Work"/>\n'
            '<bpmn:sequenceFlow id="f" sourceRef="t" targetRef="t"/>\n'
        )
    )
    assert "self-loop on 't'" in str(error)


def test_a_duplicate_flow_element_id_is_refused():
    error = caught(
        definitions(
            '<bpmn:task id="t" name="First"/>\n<bpmn:task id="t" name="Second"/>\n'
        )
    )
    assert "declared more than once" in str(error)


def test_a_dtd_is_refused_rather_than_expanded():
    source = (
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE definitions [<!ENTITY boom 'x'>]>\n"
        f"<bpmn:definitions {NS}/>"
    )
    assert "declares a DTD" in str(caught(source))


def test_a_missing_file_is_a_clean_import_error(tmp_path):
    assert "looks like a path but no such file exists" in str(
        caught(str(tmp_path / "absent.bpmn"))
    )


def test_a_non_string_source_is_a_type_error():
    with pytest.raises(TypeError):
        flowyaml.read_bpmn(42)  # type: ignore[arg-type]
