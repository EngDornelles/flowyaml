"""Normalization shared by every FlowYAML v0 importer.

An importer's job is to turn a foreign notation into the *existing* FlowYAML
document shape and nothing else. It never builds a :class:`Model` directly:
it builds plain documents, serializes them with the canonical serializer, and
hands the text to the same validator every hand written source goes through.
That is what makes "importer output passes validation" a property of the
design rather than a promise.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..errors import FlowYAMLImportError
from ..model import Diagram
from ..serialize import documents_to_yaml
from ..validation import build

__all__ = [
    "TAG_LIMIT",
    "IdAllocator",
    "clean_label",
    "edge_text_fields",
    "resolve_source",
    "safe_id",
    "to_diagram",
]

#: Longest edge text that still fits the on-canvas chip. Anything longer
#: becomes a detailed label, which the renderer shortens for the chip and
#: shows in full on hover.
TAG_LIMIT = 24

#: Identifier characters FlowYAML carries safely into a JSON payload, a URL
#: hash and a DOM data attribute. Everything else is normalized away.
_UNSAFE_ID = re.compile(r"[^A-Za-z0-9_.:-]+")

_LINE_BREAK = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def safe_id(raw: str | None, fallback: str) -> str:
    """Return ``raw`` when it is already a safe identifier, else normalize it.

    Preserving the source identifier is the point: a BPMN ``Activity_0x9f2c``
    or a Mermaid ``check_stock`` stays exactly itself, so an imported document
    can still be diffed against the notation it came from. Only characters
    that would have to be escaped downstream are folded to ``_``.
    """
    text = (raw or "").strip()
    if not text:
        return fallback
    normalized = _UNSAFE_ID.sub("_", text)
    normalized = normalized.strip("_") or fallback
    if normalized[0].isdigit():
        # A leading digit is legal in FlowYAML but reads badly as a hash
        # fragment, so it gets a stable prefix rather than a random one.
        normalized = f"n{normalized}"
    return normalized


class IdAllocator:
    """Hands out unique identifiers, deterministically, in source order."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._resolved: dict[str, str] = {}

    def allocate(self, raw: str | None, fallback: str) -> str:
        base = safe_id(raw, fallback)
        candidate = base
        counter = 2
        while candidate in self._used:
            candidate = f"{base}_{counter}"
            counter += 1
        self._used.add(candidate)
        if raw:
            self._resolved.setdefault(raw, candidate)
        return candidate

    def resolve(self, raw: str) -> str | None:
        """Return the allocated identifier for a source identifier."""
        return self._resolved.get(raw)

    def __contains__(self, candidate: object) -> bool:
        return candidate in self._used


def clean_label(text: str | None, *, unescape: bool = True) -> str:
    """Return display text for a label taken from a foreign notation.

    ``<br>`` becomes a real line break, HTML entities are decoded, trailing
    whitespace leaves every line, and the result is stripped. Interior line
    structure survives, because FlowYAML renders a detailed label in a
    ``pre-wrap`` tooltip.
    """
    if not text:
        return ""
    value = _LINE_BREAK.sub("\n", text)
    if unescape:
        value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in value.split("\n")]
    return "\n".join(lines).strip()


def edge_text_fields(text: str | None) -> tuple[str, str]:
    """Split edge text into ``(tag, label)``.

    Short single-line text becomes a ``tag``, which the renderer draws as the
    compact chip verbatim. Longer or multi-line text becomes a ``label``,
    which the renderer shortens for the chip and shows in full on hover. Both
    branches are lossless; only the presentation differs.
    """
    value = clean_label(text)
    if not value:
        return "", ""
    compact = " ".join(value.split())
    if compact == value and len(compact) <= TAG_LIMIT:
        return compact, ""
    return "", value


def resolve_source(
    source: str | os.PathLike[str],
    *,
    suffixes: Sequence[str],
    source_format: str,
    text_hints: Sequence[str] = (),
) -> tuple[str, str | None]:
    """Return ``(text, source_name)`` for an importer argument.

    A :class:`~pathlib.Path` is always read from disk. A ``str`` is read from
    disk only when it is a single line with one of ``suffixes`` that exists,
    which keeps ``read_mermaid("workflow.mmd")`` convenient without ever
    guessing about real diagram text.
    """
    if isinstance(source, Path) or (
        isinstance(source, os.PathLike) and not isinstance(source, str)
    ):
        path = Path(source)
        try:
            return path.read_text(encoding="utf-8"), path.name
        except OSError as error:
            raise FlowYAMLImportError(
                f"cannot read {path}: {error}",
                source_format=source_format,
                source_name=path.name,
            ) from error
    if not isinstance(source, str):
        raise TypeError(f"source must be str or PathLike, not {type(source).__name__}")

    stripped = source.strip()
    looks_like_text = any(stripped.startswith(hint) for hint in text_hints)
    looks_like_path = (
        not looks_like_text
        and "\n" not in source
        and len(source) < 4096
        and stripped.lower().endswith(tuple(suffixes))
    )
    if looks_like_path:
        candidate = Path(source)
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8"), candidate.name
        except OSError as error:
            raise FlowYAMLImportError(
                f"cannot read {candidate}: {error}",
                source_format=source_format,
                source_name=candidate.name,
            ) from error
        raise FlowYAMLImportError(
            f"{source!r} looks like a path but no such file exists",
            source_format=source_format,
        )
    return source, None


def to_diagram(
    documents: Sequence[Mapping[str, Any]],
    *,
    source_format: str,
    source_name: str | None,
) -> Diagram:
    """Validate imported documents through the canonical FlowYAML pipeline."""
    if not documents:
        raise FlowYAMLImportError(
            "the source contains no importable process",
            source_format=source_format,
            source_name=source_name,
        )
    diagram, issues = build(documents_to_yaml(documents))
    if issues or diagram is None:
        raise FlowYAMLImportError(
            "the imported graph is not valid FlowYAML",
            source_format=source_format,
            source_name=source_name,
            issues=issues,
        )
    return diagram
