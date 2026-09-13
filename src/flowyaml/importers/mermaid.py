"""Mermaid flowchart importer for FlowYAML v0.

Scope is the ``graph`` / ``flowchart`` diagram type: direction declarations,
node shapes, labelled links, branching chains, ``&`` node groups and
subgraphs. Styling, class and click statements are read and discarded, because
FlowYAML owns its own theme. Every other Mermaid diagram type is refused with a
:class:`~flowyaml.errors.FlowYAMLImportError` that names what it found.

The importer emits no geometry. Mermaid has no coordinates to carry, and
FlowYAML lays a graph out in the browser, so the imported document is pure
graph structure.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

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

__all__ = ["read_mermaid", "MERMAID_SUFFIXES"]

FORMAT = "mermaid"

#: Suffixes that make a bare string argument a path instead of diagram text.
MERMAID_SUFFIXES = (".mmd", ".mermaid")

_HEADER = re.compile(
    r"^(?:graph|flowchart(?:-elk)?)(?:\s+(?P<direction>TB|TD|BT|RL|LR)\b)?\s*$",
    re.IGNORECASE,
)

_KNOWN_DIAGRAMS = (
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "gitGraph",
    "mindmap",
    "timeline",
    "quadrantChart",
    "requirementDiagram",
    "C4Context",
    "sankey-beta",
    "block-beta",
    "xychart-beta",
)

#: Statement keywords that carry presentation, not structure.
_IGNORED_KEYWORDS = (
    "style",
    "classdef",
    "class",
    "linkstyle",
    "click",
    "direction",
)

# --------------------------------------------------------------------------- #
# link tokens
#
# Mermaid's own lexer resolves the "---" / "-- text --" ambiguity by length: a
# plain link is at least three characters ("---", "-->", "--o"), while a bare
# "--" can only be the opening half of a link that carries inline text. The
# patterns below encode exactly that rule, which is why "A --- B --- C" reads
# as a chain and "A -- yes --> B" reads as one labelled link.
# --------------------------------------------------------------------------- #

_INVISIBLE = re.compile(r"~{3,}")
_DOTTED_PLAIN = re.compile(r"-\.+-(?P<tail>[xo>])?")
_DOTTED_TEXT = re.compile(r"-\.\s*(?P<text>(?:[^.]|\.(?!-))+?)\s*\.-+(?P<tail>[xo>])?")
_THICK_PLAIN = re.compile(r"={2,}(?P<tail>[=xo>])")
_THICK_TEXT = re.compile(r"==\s*(?P<text>(?:[^=]|=(?!=))+?)\s*={2,}(?P<tail>[xo>])?")
_DASH_PLAIN = re.compile(r"-{2,}(?P<tail>[-xo>])")
_DASH_TEXT = re.compile(r"--\s*(?P<text>(?:[^-]|-(?!-))+?)\s*-{2,}(?P<tail>[xo>])?")

_LINK_PATTERNS: tuple[tuple[re.Pattern[str], bool, bool], ...] = (
    (_INVISIBLE, True, False),
    (_DOTTED_PLAIN, True, False),
    (_DOTTED_TEXT, True, True),
    (_THICK_PLAIN, False, False),
    (_THICK_TEXT, False, True),
    (_DASH_PLAIN, False, False),
    (_DASH_TEXT, False, True),
)

#: A node identifier stops at whitespace, a shape delimiter, a group separator
#: or the first character of a link. A hyphen belongs to the identifier only
#: when it cannot begin a link.
_IDENTIFIER = re.compile(r"(?:[^\s\[\](){}<>|&;:@\"~=-]|-(?![-.>=]))+")

_CLASS_SUFFIX = re.compile(r":::[A-Za-z0-9_-]+")

_SUBGRAPH_WITH_TITLE = re.compile(r"^(?P<id>\S+)\s*\[(?P<title>.*)\]$")

_EXTENDED_SHAPE = "the extended '@{ shape: ... }' node syntax is not supported in v0"

#: Mermaid's own escape spelling, which uses "#" where HTML uses "&".
_MERMAID_ENTITY = re.compile(r"#(x[0-9A-Fa-f]+|[0-9]+|[A-Za-z]+);")
_MERMAID_NAMED = {
    "quot": '"',
    "apos": "'",
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "hash": "#",
    "nbsp": " ",
    "semi": ";",
    "colon": ":",
    "lbrace": "{",
    "rbrace": "}",
    "lpar": "(",
    "rpar": ")",
    "lbrack": "[",
    "rbrack": "]",
}

#: Shape openers, longest first, mapped to their accepted closers and the
#: FlowYAML node type they mean. "circle" and "stadium" are resolved later
#: from node degree, because Mermaid uses one shape for all three event kinds.
_SHAPES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("(((", (")))",), "endEvent"),
    ("([", ("])",), "stadium"),
    ("((", ("))",), "circle"),
    ("[[", ("]]",), "subprocess"),
    ("[(", (")]",), "state"),
    ("[/", ("/]", "\\]"), "state"),
    ("[\\", ("\\]", "/]"), "state"),
    ("{{", ("}}",), "gateway"),
    ("[", ("]",), "task"),
    ("(", (")",), "task"),
    ("{", ("}",), "gateway"),
    (">", ("]",), "intermediateEvent"),
)

#: Shapes that already name a FlowYAML node type outright.
_DIRECT_TYPES = {
    "task",
    "state",
    "gateway",
    "subprocess",
    "intermediateEvent",
    "endEvent",
}

#: Node types whose label may stay empty, matching the validator's rule.
_LABEL_OPTIONAL = ("gateway", "intermediateEvent")


@dataclass
class _Link:
    text: str = ""
    dotted: bool = False


@dataclass
class _RawNode:
    key: str
    order: int
    label: str | None = None
    shape: str | None = None
    group: str | None = None


@dataclass
class _RawEdge:
    source: str
    target: str
    text: str
    dotted: bool
    line: int


@dataclass
class _Subgraph:
    id: str
    title: str
    line: int


@dataclass
class _Statement:
    line: int
    text: str


@dataclass
class _Parsed:
    direction: str = ""
    title: str = ""
    nodes: dict[str, _RawNode] = field(default_factory=dict)
    edges: list[_RawEdge] = field(default_factory=list)
    subgraphs: dict[str, _Subgraph] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #


def read_mermaid(
    source: str | os.PathLike[str],
    *,
    model_id: str | None = None,
    name: str | None = None,
) -> Diagram:
    """Import a Mermaid flowchart into the normalized FlowYAML model.

    Parameters
    ----------
    source:
        Mermaid text, or a path to a ``.mmd`` / ``.mermaid`` file.
    model_id:
        ``meta.id`` for the produced model. Defaults to the file stem, or to
        ``"flowchart"`` when the diagram came from text.
    name:
        ``meta.name``. Defaults to the diagram's frontmatter ``title``.

    Returns
    -------
    Diagram
        The same validated model :func:`flowyaml.render` and
        :func:`flowyaml.write_html` already accept.

    Raises
    ------
    FlowYAMLImportError
        For a non-flowchart diagram, a malformed statement, an unsupported
        construct, or a graph that FlowYAML itself rejects.
    """
    text, source_name = resolve_source(
        source,
        suffixes=MERMAID_SUFFIXES,
        source_format=FORMAT,
        text_hints=("graph", "flowchart", "---"),
    )
    parser = _Parser(text, source_name)
    parsed = parser.parse()
    document = _to_document(
        parsed, parser, model_id=model_id, name=name, source_name=source_name
    )
    return to_diagram([document], source_format=FORMAT, source_name=source_name)


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #


class _Parser:
    """A single-pass scanner for one Mermaid flowchart source."""

    def __init__(self, text: str, source_name: str | None):
        self.source_name = source_name
        self.raw = text
        self.result = _Parsed()

    def fail(self, message: str, line: int | None = None) -> FlowYAMLImportError:
        return FlowYAMLImportError(
            message,
            source_format=FORMAT,
            source_name=self.source_name,
            line=line,
        )

    # -- driver ------------------------------------------------------------- #

    def parse(self) -> _Parsed:
        body, frontmatter = self._split_frontmatter(self.raw)
        title = frontmatter.get("title")
        if isinstance(title, str):
            self.result.title = clean_label(title)

        statements = _statements(body)
        if not statements:
            raise self.fail("the source contains no Mermaid statement")

        header = statements[0]
        match = _HEADER.match(header.text)
        if match is None:
            raise self.fail(_unsupported_header(header.text), header.line)
        self.result.direction = (match.group("direction") or "").upper()

        stack: list[str] = []
        for statement in statements[1:]:
            self._statement(statement, stack)
        if stack:
            raise self.fail(
                f"subgraph {stack[-1]!r} is never closed with 'end'",
                self.result.subgraphs[stack[-1]].line,
            )
        return self.result

    def _statement(self, statement: _Statement, stack: list[str]) -> None:
        text = statement.text
        lowered = text.lower()
        if lowered == "end":
            if not stack:
                raise self.fail("'end' without an open subgraph", statement.line)
            stack.pop()
            return
        if lowered.startswith("subgraph"):
            self._subgraph(text[len("subgraph"):].strip(), statement.line, stack)
            return
        words = lowered.split()
        first = words[0] if words else ""
        if first in _IGNORED_KEYWORDS or first.startswith("acc"):
            return
        self._chain(statement, stack[-1] if stack else None)

    def _subgraph(self, rest: str, line: int, stack: list[str]) -> None:
        if not rest:
            identifier = f"subgraph_{len(self.result.subgraphs) + 1}"
            title = ""
        else:
            match = _SUBGRAPH_WITH_TITLE.match(rest)
            if match is not None:
                identifier = match.group("id")
                title = _label_text(match.group("title"))
            elif " " in rest or _shape_at(rest, 0) is not None:
                identifier = f"subgraph_{len(self.result.subgraphs) + 1}"
                title = _label_text(rest)
            else:
                identifier = rest
                title = _label_text(rest)
        if identifier in self.result.subgraphs:
            raise self.fail(f"subgraph id {identifier!r} is declared twice", line)
        self.result.subgraphs[identifier] = _Subgraph(identifier, title, line)
        stack.append(identifier)

    # -- chains ------------------------------------------------------------- #

    def _chain(self, statement: _Statement, group: str | None) -> None:
        text = statement.text
        line = statement.line
        index = 0
        groups: list[list[str]] = []
        links: list[_Link] = []

        while True:
            index, keys = self._node_group(text, index, line, group)
            groups.append(keys)
            index = _skip_space(text, index)
            if index >= len(text):
                break
            link, index = self._link(text, index, line)
            links.append(link)

        for position, link in enumerate(links):
            for source in groups[position]:
                for target in groups[position + 1]:
                    self.result.edges.append(
                        _RawEdge(source, target, link.text, link.dotted, line)
                    )

    def _node_group(
        self, text: str, index: int, line: int, group: str | None
    ) -> tuple[int, list[str]]:
        keys: list[str] = []
        while True:
            index, key = self._node(text, index, line, group)
            keys.append(key)
            index = _skip_space(text, index)
            if index < len(text) and text[index] == "&":
                index += 1
                continue
            return index, keys

    def _node(
        self, text: str, index: int, line: int, group: str | None
    ) -> tuple[int, str]:
        index = _skip_space(text, index)
        if text.startswith("@{", index):
            raise self.fail(_EXTENDED_SHAPE, line)
        match = _IDENTIFIER.match(text, index)
        if match is None:
            raise self.fail(
                f"expected a node identifier near {text[index:index + 24]!r}", line
            )
        key = match.group()
        index = match.end()

        label: str | None = None
        shape: str | None = None
        opener = _shape_at(text, index)
        if opener is not None:
            index, label, shape = self._shape(text, index, opener, line)

        if text.startswith("@{", index):
            raise self.fail(_EXTENDED_SHAPE, line)
        class_match = _CLASS_SUFFIX.match(text, index)
        if class_match is not None:
            index = class_match.end()

        self._register(key, label, shape, group)
        return index, key

    def _shape(
        self,
        text: str,
        index: int,
        opener: tuple[str, tuple[str, ...], str],
        line: int,
    ) -> tuple[int, str, str]:
        open_token, closers, shape = opener
        start = index + len(open_token)
        cursor = start
        quoted = False
        while cursor < len(text):
            character = text[cursor]
            if character == '"':
                quoted = not quoted
                cursor += 1
                continue
            if not quoted:
                for closer in closers:
                    if text.startswith(closer, cursor):
                        inner = text[start:cursor]
                        return cursor + len(closer), _label_text(inner), shape
            cursor += 1
        expected = " or ".join(repr(item) for item in closers)
        raise self.fail(
            f"node shape opened with {open_token!r} is never closed with {expected}",
            line,
        )

    def _register(
        self,
        key: str,
        label: str | None,
        shape: str | None,
        group: str | None,
    ) -> None:
        node = self.result.nodes.get(key)
        if node is None:
            # Mermaid places a node in the subgraph that mentions it first, so
            # a later reference from inside a subgraph never moves it.
            node = _RawNode(key=key, order=len(self.result.nodes), group=group)
            self.result.nodes[key] = node
        # The first explicit declaration wins, so a later bare reference in a
        # chain can never quietly erase a shape or a label.
        if shape is not None and node.shape is None:
            node.shape = shape
            node.label = label
        elif label is not None and node.label is None:
            node.label = label

    # -- links -------------------------------------------------------------- #

    def _link(self, text: str, index: int, line: int) -> tuple[_Link, int]:
        if text[index] == "<":
            # A bidirectional link becomes one FlowYAML edge in the written
            # direction; v0 has no two-headed arrow.
            index += 1
        for pattern, dotted, carries_text in _LINK_PATTERNS:
            match = pattern.match(text, index)
            if match is None:
                continue
            body = _label_text(match.group("text")) if carries_text else ""
            cursor, piped = self._pipe_text(text, match.end(), line)
            return _Link(text=piped or body, dotted=dotted), cursor
        raise self.fail(f"cannot read a link near {text[index:index + 24]!r}", line)

    def _pipe_text(self, text: str, index: int, line: int) -> tuple[int, str]:
        cursor = _skip_space(text, index)
        if cursor >= len(text) or text[cursor] != "|":
            return index, ""
        cursor += 1
        start = cursor
        quoted = False
        while cursor < len(text):
            character = text[cursor]
            if character == '"':
                quoted = not quoted
            elif character == "|" and not quoted:
                return cursor + 1, _label_text(text[start:cursor])
            cursor += 1
        raise self.fail("edge text opened with '|' is never closed", line)

    # -- frontmatter -------------------------------------------------------- #

    def _split_frontmatter(self, text: str) -> tuple[str, dict[str, Any]]:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines or lines[0].strip() != "---":
            return "\n".join(lines), {}
        for position in range(1, len(lines)):
            if lines[position].strip() in ("---", "..."):
                block = "\n".join(lines[1:position])
                try:
                    data = yaml.safe_load(block)
                except yaml.YAMLError as error:
                    raise self.fail(
                        f"the frontmatter block is not valid YAML: {error}", 1
                    ) from error
                # Blank lines keep every later statement on its real line, so
                # an error still points at the line the reader sees.
                rest = ["" for _ in range(position + 1)] + lines[position + 1:]
                return "\n".join(rest), data if isinstance(data, dict) else {}
        return "\n".join(lines), {}


# --------------------------------------------------------------------------- #
# document assembly
# --------------------------------------------------------------------------- #


def _to_document(
    parsed: _Parsed,
    parser: _Parser,
    *,
    model_id: str | None,
    name: str | None,
    source_name: str | None,
) -> dict[str, Any]:
    if not parsed.nodes:
        raise parser.fail("the flowchart declares no node")

    collision = set(parsed.nodes) & set(parsed.subgraphs)
    if collision:
        offender = sorted(collision)[0]
        raise parser.fail(
            f"subgraph {offender!r} is also used as a node; v0 has no group "
            "shape, so a subgraph cannot be an edge endpoint",
            parsed.subgraphs[offender].line,
        )

    incoming = {key: 0 for key in parsed.nodes}
    outgoing = {key: 0 for key in parsed.nodes}
    for edge in parsed.edges:
        outgoing[edge.source] += 1
        incoming[edge.target] += 1

    allocator = IdAllocator()
    nodes: list[dict[str, Any]] = []
    for raw in sorted(parsed.nodes.values(), key=lambda item: item.order):
        node_type = _resolve_type(raw, incoming[raw.key], outgoing[raw.key])
        label = raw.label if raw.label is not None else raw.key
        if not label and node_type not in _LABEL_OPTIONAL:
            label = raw.key
        entry: dict[str, Any] = {
            "id": allocator.allocate(raw.key, f"node_{raw.order + 1}"),
            "type": node_type,
            "label": label,
        }
        if raw.group is not None:
            entry["group"] = raw.group
        nodes.append(entry)

    edges: list[dict[str, Any]] = []
    for edge in parsed.edges:
        source = allocator.resolve(edge.source)
        target = allocator.resolve(edge.target)
        if source == target:
            raise parser.fail(
                f"self-loop on node {edge.source!r} is not supported in v0", edge.line
            )
        entry = {"from": source, "to": target}
        tag, label = edge_text_fields(edge.text)
        if tag:
            entry["tag"] = tag
        if label:
            entry["label"] = label
        if edge.dotted:
            entry["kind"] = "association"
            entry["style"] = "dotted"
        edges.append(entry)

    stem = source_name.rsplit(".", 1)[0] if source_name else None
    meta: dict[str, Any] = {"id": safe_id(model_id or stem, "flowchart")}
    title = name if name is not None else parsed.title
    if title:
        meta["name"] = title
    meta["source_format"] = FORMAT
    if parsed.direction:
        meta["source_direction"] = parsed.direction

    document: dict[str, Any] = {"meta": meta}
    if parsed.subgraphs:
        document["groups"] = [
            {"id": item.id, "title": item.title or item.id}
            for item in parsed.subgraphs.values()
        ]
    document["nodes"] = nodes
    document["edges"] = edges
    return document


def _resolve_type(raw: _RawNode, incoming: int, outgoing: int) -> str:
    shape = raw.shape
    if shape is None:
        return "task"
    if shape in _DIRECT_TYPES:
        return shape
    # A Mermaid circle or stadium is the whole event family at once, so its
    # role comes from the graph: nothing arrives at a start, nothing leaves an
    # end, and anything in between is an intermediate event.
    if incoming == 0:
        return "startEvent"
    if outgoing == 0:
        return "endEvent"
    return "intermediateEvent"


# --------------------------------------------------------------------------- #
# lexical helpers
# --------------------------------------------------------------------------- #


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _shape_at(text: str, index: int) -> tuple[str, tuple[str, ...], str] | None:
    for opener in _SHAPES:
        if text.startswith(opener[0], index):
            return opener
    return None


def _mermaid_entity(match: re.Match[str]) -> str:
    body = match.group(1)
    if body.lower().startswith("x"):
        try:
            return chr(int(body[1:], 16))
        except ValueError:  # pragma: no cover - defensive
            return match.group(0)
    if body.isdigit():
        try:
            return chr(int(body))
        except ValueError:  # pragma: no cover - defensive
            return match.group(0)
    return _MERMAID_NAMED.get(body.lower(), match.group(0))


def _label_text(raw: str | None) -> str:
    if raw is None:
        return ""
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    text = _MERMAID_ENTITY.sub(_mermaid_entity, text)
    return clean_label(text)


def _statements(text: str) -> list[_Statement]:
    """Split a Mermaid body into statements, honouring quotes and comments."""
    statements: list[_Statement] = []
    buffer: list[str] = []
    line = 1
    start = 1
    quoted = False
    depth = 0
    index = 0
    size = len(text)

    while index < size:
        character = text[index]
        if quoted:
            buffer.append(character)
            if character == '"':
                quoted = False
            index += 1
            continue
        if character == '"':
            if not buffer:
                start = line
            quoted = True
            buffer.append(character)
            index += 1
            continue
        if character == "%" and text.startswith("%%", index):
            newline = text.find("\n", index)
            index = size if newline < 0 else newline
            continue
        if character == "\n" or (character == ";" and depth == 0):
            statement = "".join(buffer).strip()
            if statement:
                statements.append(_Statement(start, statement))
            buffer = []
            depth = 0
            if character == "\n":
                line += 1
            start = line
            index += 1
            continue
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        if not buffer and not character.isspace():
            start = line
        buffer.append(character)
        index += 1

    statement = "".join(buffer).strip()
    if statement:
        statements.append(_Statement(start, statement))
    return statements


def _unsupported_header(text: str) -> str:
    words = text.split()
    first = words[0] if words else text
    for known in _KNOWN_DIAGRAMS:
        if first.lower() == known.lower():
            return (
                f"{known} is not a flowchart; FlowYAML v0 imports "
                "'graph' and 'flowchart' diagrams only"
            )
    return (
        f"expected a 'graph' or 'flowchart' declaration, found {text!r}; "
        "FlowYAML v0 imports Mermaid flowcharts only"
    )
