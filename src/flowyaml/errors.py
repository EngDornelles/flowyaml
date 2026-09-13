"""Error and diagnostic types for FlowYAML v0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "ValidationIssue",
    "FlowYAMLError",
    "FlowYAMLValidationError",
    "FlowYAMLModelError",
    "FlowYAMLOptionError",
    "FlowYAMLImportError",
]


@dataclass(frozen=True)
class ValidationIssue:
    """A single structured problem found in a FlowYAML source.

    Attributes
    ----------
    code:
        Stable dotted identifier, for example ``node.type.unsupported``.
    message:
        Human readable description.
    model_id:
        ``meta.id`` of the offending model when it is known.
    document_index:
        Zero based index of the YAML document inside the source.
    field:
        Dotted path of the offending field, for example ``nodes[2].type``.
    line / column:
        One based YAML source position when the position is recoverable.
    severity:
        Always ``"error"`` in v0. Present so later versions can add warnings
        without changing the public shape.
    """

    code: str
    message: str
    model_id: str | None = None
    document_index: int | None = None
    field: str | None = None
    line: int | None = None
    column: int | None = None
    severity: str = "error"

    @property
    def location(self) -> str:
        """Compact ``document/model/field/line:column`` description."""
        parts: list[str] = []
        if self.document_index is not None:
            parts.append(f"document {self.document_index}")
        if self.model_id:
            parts.append(f"model {self.model_id!r}")
        if self.field:
            parts.append(self.field)
        if self.line is not None:
            pos = f"line {self.line}"
            if self.column is not None:
                pos += f", column {self.column}"
            parts.append(pos)
        return " / ".join(parts) if parts else "source"

    def __str__(self) -> str:  # pragma: no cover - exercised through messages
        return f"[{self.code}] {self.location}: {self.message}"


class FlowYAMLError(Exception):
    """Base class for every error raised by the package."""


class FlowYAMLValidationError(FlowYAMLError):
    """Raised when a source fails validation and rendering cannot continue."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues: tuple[ValidationIssue, ...] = tuple(issues)
        count = len(self.issues)
        noun = "issue" if count == 1 else "issues"
        listing = "\n".join(f"  - {issue}" for issue in self.issues)
        super().__init__(f"FlowYAML source rejected with {count} {noun}:\n{listing}")


class FlowYAMLModelError(FlowYAMLError, LookupError):
    """Raised when a requested ``model_id`` is not present in the source."""


class FlowYAMLOptionError(FlowYAMLError, ValueError):
    """Raised for unsupported public API option values."""


class FlowYAMLImportError(FlowYAMLError, ValueError):
    """Raised when a foreign source cannot be imported into FlowYAML.

    The importers never emit a half-built graph. Anything they cannot map onto
    the v0 contract - an unsupported diagram type, a malformed link, an
    unresolved reference - stops with this error, which names the format, the
    source, and the position when the position is recoverable.

    Attributes
    ----------
    source_format:
        ``"mermaid"`` or ``"bpmn"``.
    source_name:
        The file the text came from, when it came from a file.
    line / column:
        One based position in the imported source, when recoverable.
    issues:
        Validation issues, on the rare path where a syntactically importable
        source normalizes to a graph FlowYAML still rejects.
    """

    def __init__(
        self,
        message: str,
        *,
        source_format: str | None = None,
        source_name: str | None = None,
        line: int | None = None,
        column: int | None = None,
        issues: Iterable[ValidationIssue] = (),
    ):
        self.source_format = source_format
        self.source_name = source_name
        self.line = line
        self.column = column
        self.issues: tuple[ValidationIssue, ...] = tuple(issues)

        head = f"{source_format} import failed" if source_format else "import failed"
        where: list[str] = []
        if source_name:
            where.append(str(source_name))
        if line is not None:
            position = f"line {line}"
            if column is not None:
                position += f", column {column}"
            where.append(position)
        if where:
            head += " (" + ", ".join(where) + ")"
        text = f"{head}: {message}"
        if self.issues:
            listing = "\n".join(f"  - {issue}" for issue in self.issues)
            text += "\n" + listing
        super().__init__(text)
