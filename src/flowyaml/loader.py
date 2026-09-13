"""Multi-document YAML loading with recoverable source positions.

PyYAML's high level ``safe_load_all`` discards node marks, so FlowYAML composes
the document graph itself and records a ``(line, column)`` position for every
reachable path. Validation then reports the offending field with the position
that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from .errors import ValidationIssue

__all__ = ["RawDocument", "parse_documents"]

_MAX_DEPTH = 200

Path = tuple[Any, ...]


@dataclass
class RawDocument:
    """One composed YAML document plus its position table."""

    index: int
    data: Any
    positions: dict[Path, tuple[int, int]] = field(default_factory=dict)

    def position(self, *path: Any) -> tuple[int | None, int | None]:
        """Return the ``(line, column)`` of ``path``, falling back to parents."""
        probe: Path = tuple(path)
        while True:
            found = self.positions.get(probe)
            if found is not None:
                return found
            if not probe:
                return (None, None)
            probe = probe[:-1]

    @property
    def is_blank(self) -> bool:
        return self.data is None


def parse_documents(text: str) -> tuple[list[RawDocument], list[ValidationIssue]]:
    """Compose every YAML document in ``text``.

    Returns the documents that parsed plus any syntax level issues. A syntax
    error stops parsing at the failing document, matching PyYAML's stream
    semantics, and is reported with its source position.
    """
    issues: list[ValidationIssue] = []
    documents: list[RawDocument] = []

    loader = yaml.SafeLoader(text)
    try:
        index = 0
        while True:
            try:
                if not loader.check_node():
                    break
                node = loader.get_node()
            except yaml.MarkedYAMLError as exc:
                mark = exc.problem_mark or exc.context_mark
                issues.append(
                    ValidationIssue(
                        code="yaml.syntax",
                        message=(exc.problem or "invalid YAML").strip(),
                        document_index=index,
                        line=(mark.line + 1) if mark else None,
                        column=(mark.column + 1) if mark else None,
                    )
                )
                break
            except yaml.YAMLError as exc:  # pragma: no cover - defensive
                issues.append(
                    ValidationIssue(
                        code="yaml.syntax",
                        message=str(exc),
                        document_index=index,
                    )
                )
                break

            if node is None:
                documents.append(RawDocument(index=index, data=None))
                index += 1
                continue

            document = RawDocument(index=index, data=None)
            try:
                document.data = _convert(loader, node, (), document.positions, 0, set())
            except yaml.MarkedYAMLError as exc:
                mark = exc.problem_mark or exc.context_mark
                issues.append(
                    ValidationIssue(
                        code="yaml.syntax",
                        message=(exc.problem or str(exc)).strip(),
                        document_index=index,
                        line=(mark.line + 1) if mark else None,
                        column=(mark.column + 1) if mark else None,
                    )
                )
                break
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        code="yaml.unsupported",
                        message=str(exc),
                        document_index=index,
                        line=node.start_mark.line + 1,
                        column=node.start_mark.column + 1,
                    )
                )
                break
            documents.append(document)
            index += 1
    finally:
        loader.dispose()

    return documents, issues


def _convert(
    loader: yaml.SafeLoader,
    node: yaml.Node,
    path: Path,
    positions: dict[Path, tuple[int, int]],
    depth: int,
    seen: set[int],
) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("YAML nesting is too deep for FlowYAML to normalize")
    positions[path] = (node.start_mark.line + 1, node.start_mark.column + 1)

    if isinstance(node, yaml.MappingNode):
        if id(node) in seen:
            raise ValueError("recursive YAML anchors are not supported")
        seen = seen | {id(node)}
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            try:
                hash(key)
            except TypeError:
                raise ValueError("mapping keys must be hashable scalars") from None
            positions[path + (key, "\x00key")] = (
                key_node.start_mark.line + 1,
                key_node.start_mark.column + 1,
            )
            mapping[key] = _convert(loader, value_node, path + (key,), positions, depth + 1, seen)
        return mapping

    if isinstance(node, yaml.SequenceNode):
        if id(node) in seen:
            raise ValueError("recursive YAML anchors are not supported")
        seen = seen | {id(node)}
        return [
            _convert(loader, item, path + (position,), positions, depth + 1, seen)
            for position, item in enumerate(node.value)
        ]

    return loader.construct_object(node, deep=True)
