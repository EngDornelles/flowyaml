"""Immutable normalized graph model for FlowYAML v0."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterator, Mapping

__all__ = [
    "NODE_TYPES",
    "EDGE_KINDS",
    "EDGE_STYLES",
    "CLICKABLE_NODE_TYPES",
    "Node",
    "Edge",
    "Model",
    "Diagram",
    "freeze",
]

#: The seven node types observed in the delivered ERP DINFRA flowchart app.
NODE_TYPES: tuple[str, ...] = (
    "startEvent",
    "endEvent",
    "intermediateEvent",
    "gateway",
    "subprocess",
    "state",
    "task",
)

#: Edge kinds accepted by v0. Anything else is rejected by validation.
EDGE_KINDS: tuple[str, ...] = ("sequence", "association")

#: Edge styles accepted by v0. Anything else is rejected by validation.
EDGE_STYLES: tuple[str, ...] = ("solid", "dotted")

#: Node types that may become an in-document navigation control.
CLICKABLE_NODE_TYPES: tuple[str, ...] = ("subprocess",)


def freeze(value: Any) -> Any:
    """Return a recursively read-only view of plain YAML data."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Node:
    """One node of a single model level."""

    id: str
    type: str
    label: str
    ref: str | None = None
    detail: str | None = None
    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def is_subprocess(self) -> bool:
        return self.type in CLICKABLE_NODE_TYPES

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "type": self.type, "label": self.label}
        if self.ref:
            payload["ref"] = self.ref
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class Edge:
    """One directed connection of a single model level."""

    id: str
    source: str
    target: str
    tag: str = ""
    label: str = ""
    kind: str = "sequence"
    style: str = "solid"
    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def dotted(self) -> bool:
        """``True`` when the edge renders as a dotted association."""
        return self.kind == "association" or self.style == "dotted"

    @property
    def chip(self) -> str:
        """Compact chip text shown on the canvas."""
        if self.tag:
            return self.tag
        if self.label:
            return _shorten(self.label, 28)
        return ""

    @property
    def tooltip(self) -> str:
        """Full text shown on hover, or ``""`` when the chip already says it."""
        if not self.label:
            return ""
        if self.label == self.chip:
            return ""
        return self.label

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "from": self.source,
            "to": self.target,
            "kind": self.kind,
            "style": self.style,
            "dotted": self.dotted,
        }
        if self.chip:
            payload["chip"] = self.chip
        if self.tooltip:
            payload["tooltip"] = self.tooltip
        return payload


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "\u2026"


@dataclass(frozen=True)
class Model:
    """One YAML document, normalized into a single flow level."""

    id: str
    name: str
    version: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    meta: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    document_index: int = 0

    def node(self, node_id: str) -> Node | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    @property
    def title(self) -> str:
        return self.name or self.id

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "nodes": [node.to_payload() for node in self.nodes],
            "edges": [edge.to_payload() for edge in self.edges],
        }
        if self.version:
            payload["version"] = self.version
        date = self.meta.get("date")
        if isinstance(date, str) and date:
            payload["date"] = date
        description = self.meta.get("description")
        if isinstance(description, str) and description:
            payload["description"] = description
        return payload


@dataclass(frozen=True)
class Diagram:
    """Every model contained in one FlowYAML source."""

    models: tuple[Model, ...]

    def __iter__(self) -> Iterator[Model]:
        return iter(self.models)

    def __len__(self) -> int:
        return len(self.models)

    def __contains__(self, model_id: object) -> bool:
        return any(model.id == model_id for model in self.models)

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(model.id for model in self.models)

    @property
    def default_model(self) -> Model:
        return self.models[0]

    def get(self, model_id: str) -> Model | None:
        for model in self.models:
            if model.id == model_id:
                return model
        return None
