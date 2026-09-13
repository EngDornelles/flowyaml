"""BPMN 2.0 XML importer for FlowYAML v0.

Scope is the semantic half of a BPMN file: processes, events, tasks, gateways,
sub-processes, call activities, data references, text annotations, sequence
flows and associations. Every element is matched by its local name, so the
usual ``bpmn:``, ``bpmn2:`` and ``semantic:`` prefixes all read the same, and a
default-namespaced file reads the same again.

The ``bpmndi:BPMNDiagram`` half of the file is read past and discarded on
purpose. Diagram interchange is nothing but coordinates, and FlowYAML lays a
graph out in the browser from the real font metrics, so importing a stored
position would only fight the layout engine. No imported document carries
geometry or any other ``ui`` metadata.

An expanded ``subProcess`` becomes its own FlowYAML model, and the node that
contained it becomes a ``subprocess`` card whose ``ref`` opens that model, so
BPMN nesting arrives as FlowYAML's own in-document navigation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterator
from xml.etree import ElementTree

from ..errors import FlowYAMLImportError
from ..model import Diagram
from ._common import (
    IdAllocator,
    clean_label,
    edge_text_fields,
    resolve_source,
    safe_id,
    to_diagram,
)

__all__ = ["read_bpmn", "BPMN_SUFFIXES"]

FORMAT = "bpmn"

#: Suffixes that make a bare string argument a path instead of XML text.
BPMN_SUFFIXES = (".bpmn", ".bpmn20.xml", ".xml")

#: BPMN flow element local names, mapped to the v0 node type they mean.
NODE_TYPES: dict[str, str] = {
    "startEvent": "startEvent",
    "endEvent": "endEvent",
    "intermediateCatchEvent": "intermediateEvent",
    "intermediateThrowEvent": "intermediateEvent",
    "implicitThrowEvent": "intermediateEvent",
    "boundaryEvent": "intermediateEvent",
    "task": "task",
    "userTask": "task",
    "manualTask": "task",
    "serviceTask": "task",
    "scriptTask": "task",
    "businessRuleTask": "task",
    "sendTask": "task",
    "receiveTask": "task",
    "callActivity": "subprocess",
    "subProcess": "subprocess",
    "transaction": "subprocess",
    "adHocSubProcess": "subprocess",
    "exclusiveGateway": "gateway",
    "inclusiveGateway": "gateway",
    "parallelGateway": "gateway",
    "eventBasedGateway": "gateway",
    "complexGateway": "gateway",
    "dataObjectReference": "state",
    "dataStoreReference": "state",
    "textAnnotation": "state",
}

#: Activities whose children are a flow level of their own.
_CONTAINERS = ("subProcess", "transaction", "adHocSubProcess")

#: Container children that carry no node and no edge.
_IGNORED = frozenset(
    {
        "documentation",
        "extensionElements",
        "ioSpecification",
        "property",
        "dataObject",
        "laneSet",
        "incoming",
        "outgoing",
        "group",
        "auditing",
        "monitoring",
        "resourceRole",
        "performer",
        "potentialOwner",
        "humanPerformer",
        "artifact",
        "standardLoopCharacteristics",
        "multiInstanceLoopCharacteristics",
        "dataInput",
        "dataOutput",
        "dataInputAssociation",
        "dataOutputAssociation",
        "correlationSubscription",
        "supportedInterfaceRef",
    }
)

#: Anything unmapped whose name still reads like a flow node is refused rather
#: than dropped, because silently losing a step is worse than failing loudly.
_LOOKS_LIKE_NODE = re.compile(r"(Event|Task|Gateway|Activity|SubProcess)$")

@dataclass
class _Level:
    """One BPMN container that becomes one FlowYAML model."""

    element: ElementTree.Element
    kind: str
    xml_id: str
    model_id: str
    name: str


@dataclass
class _Bundle:
    levels: list[_Level] = field(default_factory=list)
    #: XML id of a container element -> the model id it produced.
    model_for_xml_id: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #


def read_bpmn(
    source: str | os.PathLike[str],
    *,
    model_id: str | None = None,
    name: str | None = None,
) -> Diagram:
    """Import a BPMN 2.0 XML process into the normalized FlowYAML model.

    Parameters
    ----------
    source:
        BPMN XML text, or a path to a ``.bpmn`` / ``.xml`` file.
    model_id:
        ``meta.id`` for the first process. Later processes and expanded
        sub-processes keep their own BPMN ids. Defaults to the process id.
    name:
        ``meta.name`` for the first process. Defaults to the participant name,
        then the process name, then the process id.

    Returns
    -------
    Diagram
        One model per process, followed by one model per expanded
        sub-process, in document order. Every ``subprocess`` node that owns a
        level carries the ``ref`` that opens it.

    Raises
    ------
    FlowYAMLImportError
        For XML that does not parse, a file that is not BPMN, an unsupported
        flow element, an unresolved flow reference, or a graph FlowYAML
        itself rejects.
    """
    text, source_name = resolve_source(
        source,
        suffixes=BPMN_SUFFIXES,
        source_format=FORMAT,
        text_hints=("<",),
    )
    reader = _Reader(text, source_name)
    documents = reader.read(model_id=model_id, name=name)
    return to_diagram(documents, source_format=FORMAT, source_name=source_name)


# --------------------------------------------------------------------------- #
# reader
# --------------------------------------------------------------------------- #


class _Reader:
    """Turns one BPMN definitions document into FlowYAML documents."""

    def __init__(self, text: str, source_name: str | None):
        self.text = text
        self.source_name = source_name
        #: Participant name for each referenced process id.
        self.participants: dict[str, str] = {}
        #: Message flows declared at collaboration level.
        self.message_flows: list[tuple[str, str, str]] = []

    def fail(
        self, message: str, line: int | None = None, column: int | None = None
    ) -> FlowYAMLImportError:
        return FlowYAMLImportError(
            message,
            source_format=FORMAT,
            source_name=self.source_name,
            line=line,
            column=column,
        )

    # -- driver ------------------------------------------------------------- #

    def read(self, *, model_id: str | None, name: str | None) -> list[dict[str, Any]]:
        root = self._parse()
        if _local(root.tag) != "definitions":
            raise self.fail(
                f"the document root is {_local(root.tag)!r}, not 'definitions'; "
                "FlowYAML v0 imports BPMN 2.0 files only"
            )

        for collaboration in _children(root, "collaboration"):
            for participant in _children(collaboration, "participant"):
                process_ref = participant.get("processRef")
                if process_ref:
                    self.participants[process_ref] = clean_label(
                        participant.get("name")
                    )
            for flow in _children(collaboration, "messageFlow"):
                source_ref = flow.get("sourceRef")
                target_ref = flow.get("targetRef")
                if source_ref and target_ref:
                    self.message_flows.append(
                        (source_ref, target_ref, clean_label(flow.get("name")))
                    )

        processes = list(_children(root, "process"))
        if not processes:
            raise self.fail("the definitions element declares no process")

        bundle = _Bundle()
        allocator = IdAllocator()
        for position, process in enumerate(processes):
            if not _has_flow_nodes(process):
                # A collaboration may declare an empty pool for a black box
                # participant. It carries no flow, so it produces no level.
                continue
            self._collect(process, "process", allocator, bundle, position)

        if not bundle.levels:
            raise self.fail("no process in this file declares a flow node")

        documents = [self._document(level, bundle) for level in bundle.levels]
        first = documents[0]["meta"]
        if model_id:
            wanted = safe_id(model_id, first["id"])
            for document in documents:
                for node in document["nodes"]:
                    if node.get("ref") == first["id"]:
                        node["ref"] = wanted
            first["id"] = wanted
        if name is not None:
            first["name"] = name
        return documents

    def _parse(self) -> ElementTree.Element:
        # ElementTree resolves internal entities, so a document type
        # declaration is refused outright rather than expanded. A BPMN file
        # has no legitimate use for one.
        head = self.text[:4096].lstrip()
        if "<!DOCTYPE" in head.upper():
            raise self.fail(
                "the document declares a DTD, which FlowYAML does not process"
            )
        # An XML declaration has to be the first thing in the entity, so a
        # triple quoted Python literal that opens with a newline is trimmed
        # rather than refused. The trimmed lines are added back to any
        # reported position.
        body = self.text.lstrip()
        offset = self.text[: len(self.text) - len(body)].count(chr(10))
        try:
            return ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            line, column = getattr(error, "position", (None, None))
            raise self.fail(
                f"the source is not well formed XML: {error}",
                (line + offset) if isinstance(line, int) else None,
                (column + 1) if isinstance(column, int) else None,
            ) from error

    # -- level discovery ---------------------------------------------------- #

    def _collect(
        self,
        element: ElementTree.Element,
        kind: str,
        allocator: IdAllocator,
        bundle: _Bundle,
        position: int,
    ) -> None:
        xml_id = element.get("id") or ""
        fallback = f"{kind.lower()}_{position + 1}"
        model_id = allocator.allocate(xml_id, fallback)
        if xml_id:
            bundle.model_for_xml_id[xml_id] = model_id
        bundle.levels.append(
            _Level(
                element=element,
                kind=kind,
                xml_id=xml_id,
                model_id=model_id,
                name=self._level_name(element, kind, xml_id, model_id),
            )
        )
        for index, child in enumerate(element):
            local = _local(child.tag)
            if local in _CONTAINERS and _has_flow_nodes(child):
                self._collect(child, local, allocator, bundle, index)

    def _level_name(
        self,
        element: ElementTree.Element,
        kind: str,
        xml_id: str,
        model_id: str,
    ) -> str:
        if kind == "process":
            participant = self.participants.get(xml_id, "")
            if participant:
                return participant
        return clean_label(element.get("name")) or model_id

    # -- one level ---------------------------------------------------------- #

    def _document(self, level: _Level, bundle: _Bundle) -> dict[str, Any]:
        element = level.element
        lanes = _lane_map(element)
        allocator = IdAllocator()

        nodes: list[dict[str, Any]] = []
        flows: list[ElementTree.Element] = []
        derived: list[dict[str, Any]] = []

        for position, child in enumerate(element):
            local = _local(child.tag)
            if local in ("sequenceFlow", "association"):
                flows.append(child)
                continue
            if local in NODE_TYPES:
                nodes.append(
                    self._node(child, local, position, allocator, lanes, bundle)
                )
                derived.extend(_attached_edges(child, local))
                continue
            if local in _IGNORED:
                continue
            if _LOOKS_LIKE_NODE.search(local):
                raise self.fail(
                    f"flow element {local!r} is not supported by FlowYAML v0; "
                    f"supported elements are {', '.join(sorted(NODE_TYPES))}"
                )

        if not nodes:  # pragma: no cover - guarded by _has_flow_nodes
            raise self.fail(f"{level.kind} {level.model_id!r} declares no flow node")

        edges: list[dict[str, Any]] = []
        for flow in flows:
            edge = self._flow_edge(flow, allocator, level)
            if edge is not None:
                edges.append(edge)
        edges.extend(_resolve_soft(derived, allocator))
        edges.extend(_resolve_soft(self._message_flow_items(), allocator))

        meta: dict[str, Any] = {
            "id": level.model_id,
            "name": level.name,
            "source_format": FORMAT,
            "source_element": level.kind,
        }
        document: dict[str, Any] = {"meta": meta}
        lane_names = _lane_names(element)
        if lane_names:
            document["actors"] = [
                {"id": safe_id(lane_id, f"lane_{number + 1}"), "name": lane_name}
                for number, (lane_id, lane_name) in enumerate(lane_names)
            ]
        document["nodes"] = nodes
        document["edges"] = edges
        return document

    def _message_flow_items(self) -> list[dict[str, Any]]:
        return [
            {"source": source, "target": target, "text": text}
            for source, target, text in self.message_flows
        ]

    def _node(
        self,
        child: ElementTree.Element,
        local: str,
        position: int,
        allocator: IdAllocator,
        lanes: dict[str, str],
        bundle: _Bundle,
    ) -> dict[str, Any]:
        xml_id = child.get("id") or ""
        if xml_id and allocator.resolve(xml_id) is not None:
            raise self.fail(
                f"flow element id {xml_id!r} is declared more than once in the "
                "same level"
            )
        node_id = allocator.allocate(xml_id, f"{local}_{position + 1}")
        node_type = NODE_TYPES[local]
        label = _node_label(child, local)
        if not label and node_type not in ("gateway", "intermediateEvent"):
            label = xml_id or node_id

        entry: dict[str, Any] = {"id": node_id, "type": node_type, "label": label}
        reference = self._reference(child, local, bundle)
        if reference:
            entry["ref"] = reference
        detail = _documentation(child)
        if detail:
            entry["detail"] = detail
        entry["bpmn"] = local
        lane = lanes.get(xml_id)
        if lane:
            entry["lane"] = lane
        return entry

    def _reference(
        self, child: ElementTree.Element, local: str, bundle: _Bundle
    ) -> str | None:
        if local in _CONTAINERS:
            for level in bundle.levels:
                if level.element is child:
                    return level.model_id
            return None
        if local == "callActivity":
            called = child.get("calledElement")
            if called:
                return bundle.model_for_xml_id.get(called)
        return None

    def _flow_edge(
        self, flow: ElementTree.Element, allocator: IdAllocator, level: _Level
    ) -> dict[str, Any] | None:
        local = _local(flow.tag)
        flow_id = flow.get("id") or local
        source_ref = flow.get("sourceRef")
        target_ref = flow.get("targetRef")
        soft = local == "association"

        if not source_ref or not target_ref:
            if soft:
                return None
            raise self.fail(
                f"sequenceFlow {flow_id!r} is missing 'sourceRef' or 'targetRef'"
            )
        source = allocator.resolve(source_ref)
        target = allocator.resolve(target_ref)
        if source is None or target is None:
            if soft:
                return None
            missing = source_ref if source is None else target_ref
            raise self.fail(
                f"sequenceFlow {flow_id!r} references {missing!r}, which is not a "
                f"flow node of {level.kind} {level.model_id!r}"
            )
        if source == target:
            if soft:
                return None
            raise self.fail(
                f"sequenceFlow {flow_id!r} is a self-loop on {source_ref!r}, "
                "which is not supported in v0"
            )

        text = clean_label(flow.get("name"))
        if soft:
            return _association(source, target, text)
        entry: dict[str, Any] = {"from": source, "to": target}
        tag, label = edge_text_fields(text)
        if tag:
            entry["tag"] = tag
        if label:
            entry["label"] = label
        return entry


# --------------------------------------------------------------------------- #
# element helpers
# --------------------------------------------------------------------------- #


def _local(tag: object) -> str:
    """Return an element's local name, whatever namespace prefix it used."""
    if not isinstance(tag, str):  # comments and processing instructions
        return ""
    return tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, local: str) -> Iterator[ElementTree.Element]:
    for child in element:
        if _local(child.tag) == local:
            yield child


def _has_flow_nodes(element: ElementTree.Element) -> bool:
    return any(_local(child.tag) in NODE_TYPES for child in element)


def _text_of(element: ElementTree.Element) -> str:
    return clean_label("".join(element.itertext()))


def _node_label(child: ElementTree.Element, local: str) -> str:
    if local == "textAnnotation":
        for text in _children(child, "text"):
            found = _text_of(text)
            if found:
                return found
    return clean_label(child.get("name"))


def _documentation(child: ElementTree.Element) -> str:
    parts = [_text_of(item) for item in _children(child, "documentation")]
    return "\n".join(part for part in parts if part)


def _lane_map(element: ElementTree.Element) -> dict[str, str]:
    """Return ``{flow node id: lane name}`` for one container."""
    lanes: dict[str, str] = {}
    for lane_set in _children(element, "laneSet"):
        for lane in _children(lane_set, "lane"):
            name = clean_label(lane.get("name")) or (lane.get("id") or "")
            for reference in _children(lane, "flowNodeRef"):
                value = (reference.text or "").strip()
                if value:
                    lanes.setdefault(value, name)
    return lanes


def _lane_names(element: ElementTree.Element) -> list[tuple[str, str]]:
    """Return ``(id, name)`` for every lane, in document order."""
    out: list[tuple[str, str]] = []
    for lane_set in _children(element, "laneSet"):
        for lane in _children(lane_set, "lane"):
            lane_id = lane.get("id") or ""
            name = clean_label(lane.get("name")) or lane_id
            if lane_id or name:
                out.append((lane_id, name))
    return out


def _association(source: str, target: str, text: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"from": source, "to": target}
    tag, label = edge_text_fields(text)
    if tag:
        entry["tag"] = tag
    if label:
        entry["label"] = label
    entry["kind"] = "association"
    entry["style"] = "dotted"
    return entry


def _attached_edges(child: ElementTree.Element, local: str) -> list[dict[str, Any]]:
    """Association edges implied by a node rather than declared as one."""
    out: list[dict[str, Any]] = []
    xml_id = child.get("id") or ""
    if not xml_id:
        return out
    if local == "boundaryEvent":
        attached = child.get("attachedToRef")
        if attached:
            out.append({"source": attached, "target": xml_id, "text": ""})
    for association in _children(child, "dataInputAssociation"):
        for reference in _children(association, "sourceRef"):
            value = (reference.text or "").strip()
            if value:
                out.append({"source": value, "target": xml_id, "text": ""})
    for association in _children(child, "dataOutputAssociation"):
        for reference in _children(association, "targetRef"):
            value = (reference.text or "").strip()
            if value:
                out.append({"source": xml_id, "target": value, "text": ""})
    return out


def _resolve_soft(
    items: list[dict[str, Any]], allocator: IdAllocator
) -> list[dict[str, Any]]:
    """Resolve decorative edges, dropping any end outside this level.

    A boundary attachment, a data association and a message flow all decorate
    a flow rather than carry it, so an end that lives in another level is
    dropped instead of failing the import. A sequence flow is never soft.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        source = allocator.resolve(item["source"])
        target = allocator.resolve(item["target"])
        if source is None or target is None or source == target:
            continue
        if (source, target) in seen:
            continue
        seen.add((source, target))
        out.append(_association(source, target, item["text"]))
    return out
