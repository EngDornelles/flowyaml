"""Canonical FlowYAML YAML serialization.

The importers build plain Python documents and hand them to
:func:`documents_to_yaml`, so every imported graph reaches the model through
exactly the same loader and validator as hand written YAML. The same code
serves :func:`flowyaml.to_yaml`, which turns any normalized
:class:`~flowyaml.model.Diagram` back into source text.

Nothing here ever writes layout, geometry or ``ui`` metadata. FlowYAML lays a
graph out in the browser, so a coordinate has no place in the contract.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

import yaml

from .model import Diagram, Model

__all__ = ["documents_to_yaml", "diagram_to_documents", "to_yaml", "thaw"]

#: Keys the model already owns, so they are never re-emitted from ``extra``.
_NODE_OWNED = ("id", "type", "label", "ref", "detail", "description")
_EDGE_OWNED = ("from", "to", "tag", "label", "kind", "style")
_DOCUMENT_OWNED = ("meta", "nodes", "edges")


def thaw(value: Any) -> Any:
    """Return a plain, mutable copy of a frozen model mapping."""
    if isinstance(value, (Mapping, MappingProxyType)):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def documents_to_yaml(documents: Sequence[Mapping[str, Any]]) -> str:
    """Serialize FlowYAML documents to one multi-document YAML string.

    ``width`` is deliberately enormous: PyYAML folds long plain scalars by
    default, and a folded label comes back with different internal whitespace.
    An imported label must survive the round trip byte for byte.
    """
    return yaml.safe_dump_all(
        [thaw(document) for document in documents],
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1 << 20,
    )


def _model_to_document(model: Model) -> dict[str, Any]:
    document: dict[str, Any] = {"meta": thaw(model.meta) or {"id": model.id}}
    for key, value in model.extra.items():
        if key not in _DOCUMENT_OWNED:
            document[key] = thaw(value)

    nodes: list[dict[str, Any]] = []
    for node in model.nodes:
        entry: dict[str, Any] = {"id": node.id, "type": node.type}
        entry["label"] = node.label
        if node.ref:
            entry["ref"] = node.ref
        if node.detail:
            entry["detail"] = node.detail
        for key, value in node.extra.items():
            if key not in _NODE_OWNED:
                entry[key] = thaw(value)
        nodes.append(entry)

    edges: list[dict[str, Any]] = []
    for edge in model.edges:
        entry = {"from": edge.source, "to": edge.target}
        if edge.tag:
            entry["tag"] = edge.tag
        if edge.label:
            entry["label"] = edge.label
        if edge.kind != "sequence":
            entry["kind"] = edge.kind
        if edge.style != "solid":
            entry["style"] = edge.style
        for key, value in edge.extra.items():
            if key not in _EDGE_OWNED:
                entry[key] = thaw(value)
        edges.append(entry)

    document["nodes"] = nodes
    document["edges"] = edges
    return document


def diagram_to_documents(diagram: Diagram) -> list[dict[str, Any]]:
    """Return one plain document per model, in diagram order."""
    return [_model_to_document(model) for model in diagram.models]


def to_yaml(diagram: Diagram) -> str:
    """Serialize a normalized diagram back to canonical FlowYAML YAML."""
    return documents_to_yaml(diagram_to_documents(diagram))
