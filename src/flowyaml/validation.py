"""Validation and normalization of FlowYAML sources.

Everything the public API knows about a source flows through :func:`build`,
which returns the immutable :class:`~flowyaml.model.Diagram` together with the
structured issues found on the way. ``build`` never raises for bad input; the
public API decides when issues become :class:`FlowYAMLValidationError`.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from .errors import ValidationIssue
from .loader import RawDocument, parse_documents
from .model import (
    EDGE_KINDS,
    EDGE_STYLES,
    NODE_TYPES,
    Diagram,
    Edge,
    Model,
    Node,
    freeze,
)

__all__ = ["build", "validate_source"]

#: Node types whose label is allowed to be empty. Both are connector shapes
#: in the originating source: a gateway used purely as a merge, and an
#: intermediate event used purely as a junction between branches. Every other
#: type carries process meaning and still requires text.
_LABEL_OPTIONAL_TYPES = ("gateway", "intermediateEvent")


class _Collector:
    """Accumulates issues for one document."""

    def __init__(self, document: RawDocument):
        self.document = document
        self.issues: list[ValidationIssue] = []
        self.model_id: str | None = None

    def add(self, code: str, message: str, path: tuple[Any, ...] = ()) -> None:
        line, column = self.document.position(*path)
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                model_id=self.model_id,
                document_index=self.document.index,
                field=_format_path(path) or None,
                line=line,
                column=column,
            )
        )


def _format_path(path: tuple[Any, ...]) -> str:
    out = ""
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        elif part == "\x00key":
            continue
        else:
            out += f".{part}" if out else str(part)
    return out


def build(source: str) -> tuple[Diagram | None, tuple[ValidationIssue, ...]]:
    """Parse, validate and normalize ``source``.

    Returns ``(diagram, issues)``. ``diagram`` is ``None`` when any issue was
    found, so callers never see a half-normalized graph.
    """
    documents, issues = parse_documents(source)
    all_issues: list[ValidationIssue] = list(issues)

    populated = [document for document in documents if not document.is_blank]
    if not populated and not all_issues:
        all_issues.append(
            ValidationIssue(
                code="source.empty",
                message="the source contains no YAML document with content",
            )
        )

    models: list[Model] = []
    # Every model id the source declared, including ids whose document failed a
    # later rule. Reference resolution reads this rather than the built models,
    # so one broken document yields one issue instead of also orphaning every
    # subprocess that points at it.
    declared_models: dict[str, int] = {}

    for document in populated:
        collector = _Collector(document)
        model = _build_model(document, collector, declared_models)
        all_issues.extend(collector.issues)
        if model is not None:
            models.append(model)

    if models:
        all_issues.extend(_validate_references(models, set(declared_models)))

    if all_issues:
        return None, tuple(all_issues)
    return Diagram(models=tuple(models)), ()


def validate_source(source: str) -> tuple[ValidationIssue, ...]:
    """Convenience wrapper returning only the issues."""
    return build(source)[1]


# --------------------------------------------------------------------------- #
# document level
# --------------------------------------------------------------------------- #


def _build_model(
    document: RawDocument,
    collector: _Collector,
    declared_models: dict[str, int],
) -> Model | None:
    data = document.data
    if not isinstance(data, dict):
        collector.add(
            "document.not_mapping",
            f"a FlowYAML document must be a mapping, found {_type_name(data)}",
        )
        return None

    meta = data.get("meta")
    if meta is None:
        collector.add("meta.missing", "'meta' is required and must contain 'id'", ("meta",))
        return None
    if not isinstance(meta, dict):
        collector.add(
            "meta.not_mapping",
            f"'meta' must be a mapping, found {_type_name(meta)}",
            ("meta",),
        )
        return None

    model_id = meta.get("id")
    if model_id is None:
        collector.add("meta.id.missing", "'meta.id' is required", ("meta",))
        return None
    if not isinstance(model_id, str) or not model_id.strip():
        collector.add(
            "meta.id.invalid",
            f"'meta.id' must be a nonempty string, found {_type_name(model_id)}",
            ("meta", "id"),
        )
        return None

    model_id = model_id.strip()
    collector.model_id = model_id
    if model_id in declared_models:
        collector.add(
            "meta.id.duplicate",
            f"model id {model_id!r} is already used by document "
            f"{declared_models[model_id]}",
            ("meta", "id"),
        )
        return None
    declared_models[model_id] = document.index

    nodes, declared_ids = _build_nodes(data, collector)
    # Edge resolution uses every id the source declared, including ids whose
    # node failed a later rule, so one broken node yields one issue instead of
    # cascading into every edge that touches it.
    edges = _build_edges(data, collector, declared_ids)

    if nodes is None or edges is None:
        return None

    return Model(
        id=model_id,
        name=_string_or_empty(meta.get("name")),
        version=_string_or_empty(meta.get("version")),
        nodes=tuple(nodes),
        edges=tuple(edges),
        meta=freeze(meta),
        extra=MappingProxyType(
            {
                key: freeze(value)
                for key, value in data.items()
                if key not in ("meta", "nodes", "edges")
            }
        ),
        document_index=document.index,
    )


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #


def _build_nodes(
    data: dict[str, Any], collector: _Collector
) -> tuple[list[Node] | None, set[str]]:
    """Return the normalized nodes and every node id the document declared."""
    raw = data.get("nodes")
    if raw is None:
        collector.add("nodes.missing", "'nodes' is required", ("nodes",))
        return None, set()
    if not isinstance(raw, list):
        collector.add(
            "nodes.not_list",
            f"'nodes' must be a list, found {_type_name(raw)}",
            ("nodes",),
        )
        return None, set()
    if not raw:
        collector.add("nodes.empty", "'nodes' must contain at least one node", ("nodes",))
        return None, set()

    nodes: list[Node] = []
    seen: dict[str, int] = {}
    failed = False

    for index, entry in enumerate(raw):
        path = ("nodes", index)
        if not isinstance(entry, dict):
            collector.add(
                "node.not_mapping",
                f"a node must be a mapping, found {_type_name(entry)}",
                path,
            )
            failed = True
            continue

        node_id = entry.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            collector.add(
                "node.id.missing",
                "every node needs a nonempty string 'id'",
                path + ("id",) if "id" in entry else path,
            )
            failed = True
            continue
        node_id = node_id.strip()
        if node_id in seen:
            collector.add(
                "node.id.duplicate",
                f"node id {node_id!r} is already used by nodes[{seen[node_id]}]",
                path + ("id",),
            )
            failed = True
            continue
        seen[node_id] = index

        node_type = entry.get("type")
        if node_type is None:
            collector.add("node.type.missing", f"node {node_id!r} needs a 'type'", path)
            failed = True
            continue
        if not isinstance(node_type, str) or node_type not in NODE_TYPES:
            collector.add(
                "node.type.unsupported",
                f"node {node_id!r} has unsupported type {node_type!r}; "
                f"v0 supports {', '.join(NODE_TYPES)}",
                path + ("type",),
            )
            failed = True
            continue

        label = entry.get("label", "")
        if label is None:
            label = ""
        if not isinstance(label, str):
            collector.add(
                "node.label.invalid",
                f"node {node_id!r} must have a string 'label', found "
                f"{_type_name(label)}{_quoting_hint(label)}",
                path + ("label",),
            )
            failed = True
            continue
        label = label.strip()
        if not label and node_type not in _LABEL_OPTIONAL_TYPES:
            collector.add(
                "node.label.empty",
                f"node {node_id!r} of type {node_type!r} requires a nonempty label; "
                f"only {' and '.join(_LABEL_OPTIONAL_TYPES)} nodes used purely as "
                "connectors may omit it",
                path + ("label",) if "label" in entry else path,
            )
            failed = True
            continue

        ref = entry.get("ref")
        if ref is not None:
            if not isinstance(ref, str) or not ref.strip():
                collector.add(
                    "node.ref.invalid",
                    f"node {node_id!r} has a 'ref' that is not a nonempty string",
                    path + ("ref",),
                )
                failed = True
                continue
            ref = ref.strip()
            if node_type != "subprocess":
                collector.add(
                    "node.ref.unsupported",
                    f"node {node_id!r} of type {node_type!r} cannot carry 'ref'; "
                    "only subprocess nodes reference another model",
                    path + ("ref",),
                )
                failed = True
                continue

        detail = entry.get("detail", entry.get("description"))
        if detail is not None and not isinstance(detail, str):
            collector.add(
                "node.detail.invalid",
                f"node {node_id!r} must have a string 'detail', found {_type_name(detail)}",
                path + ("detail",),
            )
            failed = True
            continue

        nodes.append(
            Node(
                id=node_id,
                type=node_type,
                label=label,
                ref=ref,
                detail=(detail.strip() or None) if isinstance(detail, str) else None,
                extra=MappingProxyType(
                    {
                        key: freeze(value)
                        for key, value in entry.items()
                        if key
                        not in ("id", "type", "label", "ref", "detail", "description")
                    }
                ),
            )
        )

    return (None if failed else nodes), set(seen)


# --------------------------------------------------------------------------- #
# edges
# --------------------------------------------------------------------------- #


def _build_edges(
    data: dict[str, Any],
    collector: _Collector,
    node_ids: set[str],
) -> list[Edge] | None:
    raw = data.get("edges")
    if raw is None:
        collector.add(
            "edges.missing", "'edges' is required (it may be an empty list)", ("edges",)
        )
        return None
    if not isinstance(raw, list):
        collector.add(
            "edges.not_list",
            f"'edges' must be a list, found {_type_name(raw)}",
            ("edges",),
        )
        return None

    edges: list[Edge] = []
    failed = False

    for index, entry in enumerate(raw):
        path = ("edges", index)
        if not isinstance(entry, dict):
            collector.add(
                "edge.not_mapping",
                f"an edge must be a mapping, found {_type_name(entry)}",
                path,
            )
            failed = True
            continue

        source = entry.get("from")
        target = entry.get("to")
        if not isinstance(source, str) or not source.strip():
            collector.add(
                "edge.from.missing",
                "every edge needs a nonempty string 'from'",
                path + ("from",) if "from" in entry else path,
            )
            failed = True
            continue
        if not isinstance(target, str) or not target.strip():
            collector.add(
                "edge.to.missing",
                "every edge needs a nonempty string 'to'",
                path + ("to",) if "to" in entry else path,
            )
            failed = True
            continue
        source = source.strip()
        target = target.strip()

        if source not in node_ids:
            collector.add(
                "edge.from.unresolved",
                f"edge source {source!r} does not resolve to a node in this model",
                path + ("from",),
            )
            failed = True
            continue
        if target not in node_ids:
            collector.add(
                "edge.to.unresolved",
                f"edge target {target!r} does not resolve to a node in this model",
                path + ("to",),
            )
            failed = True
            continue
        if source == target:
            collector.add(
                "edge.self_loop",
                f"self-loop on node {source!r} is not supported in v0",
                path,
            )
            failed = True
            continue

        tag = entry.get("tag", "")
        if tag is None:
            tag = ""
        if not isinstance(tag, str):
            collector.add(
                "edge.tag.invalid",
                f"edge 'tag' must be a string, found "
                f"{_type_name(tag)}{_quoting_hint(tag)}",
                path + ("tag",),
            )
            failed = True
            continue

        label = entry.get("label", "")
        if label is None:
            label = ""
        if not isinstance(label, str):
            collector.add(
                "edge.label.invalid",
                f"edge 'label' must be a string, found "
                f"{_type_name(label)}{_quoting_hint(label)}",
                path + ("label",),
            )
            failed = True
            continue

        kind = entry.get("kind", "sequence")
        if kind is None:
            kind = "sequence"
        if not isinstance(kind, str) or kind not in EDGE_KINDS:
            collector.add(
                "edge.kind.unsupported",
                f"edge 'kind' {kind!r} is not supported; v0 accepts {', '.join(EDGE_KINDS)}",
                path + ("kind",),
            )
            failed = True
            continue

        style = entry.get("style", "solid")
        if style is None:
            style = "solid"
        if not isinstance(style, str) or style not in EDGE_STYLES:
            collector.add(
                "edge.style.unsupported",
                f"edge 'style' {style!r} is not supported; v0 accepts {', '.join(EDGE_STYLES)}",
                path + ("style",),
            )
            failed = True
            continue

        edges.append(
            Edge(
                id=f"e{index}",
                source=source,
                target=target,
                tag=" ".join(tag.split()),
                label=label.strip(),
                kind=kind,
                style=style,
                extra=MappingProxyType(
                    {
                        key: freeze(value)
                        for key, value in entry.items()
                        if key not in ("from", "to", "tag", "label", "kind", "style")
                    }
                ),
            )
        )

    return None if failed else edges


# --------------------------------------------------------------------------- #
# cross-model references
# --------------------------------------------------------------------------- #


def _validate_references(models: list[Model], known: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for model in models:
        for index, node in enumerate(model.nodes):
            if node.ref and node.ref not in known:
                issues.append(
                    ValidationIssue(
                        code="node.ref.unresolved",
                        message=(
                            f"subprocess {node.id!r} references model {node.ref!r}, "
                            "which is not embedded in this source"
                        ),
                        model_id=model.id,
                        document_index=model.document_index,
                        field=f"nodes[{index}].ref",
                    )
                )
    return issues


def _string_or_empty(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value)


def _type_name(value: Any) -> str:
    if value is None:
        return "nothing"
    return type(value).__name__


def _quoting_hint(value: Any) -> str:
    """Point at the classic YAML trap where Yes/No/On/Off become booleans."""
    if isinstance(value, bool):
        return " (quote it: bare Yes, No, On and Off are YAML booleans)"
    return ""
