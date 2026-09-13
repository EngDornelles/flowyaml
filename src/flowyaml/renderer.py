"""HTML assembly for FlowYAML v0.

The renderer turns a normalized :class:`~flowyaml.model.Diagram` into either a
standalone document or a host-safe fragment. Both carry the same three pieces:
the escaped graph payload, the vendored ELK bundle, and the instance runtime.

``data="inline"`` is the default and keeps that artifact self-sufficient:
nothing is fetched at view time. ``data="url"`` swaps the embedded graph for a
URL the host serves, which is what lets an edited YAML file reach an already
open page. That mode adds a fourth piece, the linked-source loader, and it is
the only mode in which the output makes a request.
"""

from __future__ import annotations

import html
import json
import re
import uuid
from importlib import resources
from typing import Any, Mapping

from ._version import __version__
from .errors import FlowYAMLModelError, FlowYAMLOptionError
from .model import Diagram
from .themes import (
    DEFAULT_SCHEME,
    DEFAULT_THEME,
    SCHEMES,
    get_dark_theme,
    get_theme,
    theme_css_variables,
)

__all__ = [
    "GENERATOR",
    "LAYOUT_OPTIONS",
    "OUTPUT_MODES",
    "ASSET_MODES",
    "DATA_MODES",
    "LEVEL_MODES",
    "DEFAULT_LEVELS",
    "DEFAULT_LANG",
    "DEFAULT_POLL_MS",
    "MIN_POLL_MS",
    "UI_STRINGS",
    "render_diagram",
    "data_payload",
    "new_instance_id",
    "read_asset",
]

GENERATOR = f"flowyaml {__version__}"

OUTPUT_MODES = ("document", "fragment")

#: How the page shows where the reader is in a nested flow. ``breadcrumb`` is
#: the horizontal trail in the toolbar. ``snapshot`` replaces it with a stripe
#: of the levels above, the nearest one carrying a picture of the diagram the
#: reader came from, and adds a level counter. The stripe spends vertical room
#: to buy recall, which is worth it for a wide flow and not for a tall one, so
#: the author chooses.
LEVEL_MODES = ("breadcrumb", "snapshot")

DEFAULT_LEVELS = "breadcrumb"

#: The document language when neither ``lang`` nor ``meta.lang`` says
#: otherwise. It reaches ``<html lang>``, which is what decides a screen
#: reader's voice and a browser's hyphenation.
DEFAULT_LANG = "en"

#: v0 implements ``inline`` only. The boundary stays explicit so a future
#: ``url`` mode can point at the same vendored asset from an approved host.
ASSET_MODES = ("inline",)

#: Where the rendered page reads its graph from. ``inline`` embeds it once and
#: never asks again. ``url`` leaves it out and fetches it from the host, so the
#: page reflects the YAML file as it stands, not as it stood at render time.
DATA_MODES = ("inline", "url")

#: How often a ``url`` page asks the host whether the source changed.
DEFAULT_POLL_MS = 1000

#: A floor, so a bad option cannot turn a page into a request loop.
MIN_POLL_MS = 100

#: Schemes a linked data URL may name. A relative URL names none and is the
#: normal case; anything else would let a render option point the page at
#: something that is not a data endpoint.
_ALLOWED_URL_SCHEMES = ("http", "https")

_SCHEME_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

#: ELK options carried over from the delivered ERP DINFRA flowchart app.
LAYOUT_OPTIONS: Mapping[str, str] = {
    "elk.algorithm": "layered",
    "elk.direction": "RIGHT",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.spacing.nodeNodeBetweenLayers": "64",
    "elk.layered.spacing.edgeNodeBetweenLayers": "28",
    "elk.layered.spacing.edgeEdgeBetweenLayers": "16",
    "elk.spacing.nodeNode": "40",
    "elk.spacing.edgeNode": "24",
    "elk.spacing.edgeEdge": "16",
    "elk.spacing.edgeLabel": "4",
    "elk.edgeLabels.placement": "CENTER",
    "elk.padding": "[top=28,left=28,bottom=28,right=28]",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.layered.crossingMinimization.forceNodeModelOrder": "true",
    "elk.layered.mergeEdges": "false",
    "elk.layered.thoroughness": "12",
}

#: Every word the runtime writes that did not come from the YAML source.
#:
#: The graph speaks the author's language; without this table the furniture
#: around it would always speak English, and would always speak BPMN. Half of
#: these are read only by a screen reader, and two of them - ``open`` and
#: ``destination`` - are announced joined to the author's own label, so a
#: mismatch is heard inside a single sentence.
#:
#: ``render(strings=...)`` merges over this table, so overriding one key keeps
#: the rest. A key that is not listed here is rejected, the way an unknown
#: theme is, because a silently ignored typo would show up as English text in
#: the middle of a translated page.
UI_STRINGS: Mapping[str, str] = {
    "levels": "Flow levels",
    "back": "Back",
    "backAria": "Go up one flow level",
    "zoomIn": "Zoom in",
    "zoomOut": "Zoom out",
    "fit": "Fit",
    "fitAria": "Fit the diagram to the view",
    "open": "Open subprocess",
    "destination": "Destination",
    "showing": "Showing",
    "canvasAria": "Process flow diagram",
    # The next-levels drawer, and the snapshot stripe when it is chosen. The
    # drawer's count is written in parentheses rather than as "3 steps", so no
    # translation has to carry an English plural rule.
    "nextSteps": "Explore next steps",
    "level": "Level",
    "previousLevels": "Previous levels",
    "returnTo": "Return to",
    "hint": "Drag to pan \u00b7 wheel to zoom \u00b7 Tab and Enter open a subprocess",
    "noModel": "This document contains no renderable model.",
    "noEngine": "The bundled layout engine did not load.",
    "layoutFailed": "The layout engine could not draw this model.",
    # Linked mode only. The inline artifact never shows any of these.
    "loading": "Loading the linked YAML source\u2026",
    "sourceUnavailable": "The linked YAML source could not be read.",
    "noFetch": "This browser cannot load the linked YAML source.",
    "fileSource": (
        "This page reads its diagram from a URL, and a browser refuses that "
        "request when the page itself was opened from a file. Serve it over "
        "http instead \u2014 for example with: flowyaml serve <source>.yaml"
    ),
}

_INSTANCE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_ROOT_PLACEHOLDER = "__ROOT__"
_DATA_PLACEHOLDER = "__FLOWYAML_DATA_ID__"


def read_asset(name: str) -> str:
    """Read one vendored package asset as text."""
    return (
        resources.files("flowyaml.assets").joinpath(name).read_text(encoding="utf-8")
    )


def new_instance_id() -> str:
    """Return a fresh DOM-safe instance prefix."""
    return "fy-" + uuid.uuid4().hex[:10]


#: Characters that must not survive literally inside a script element.
#: The replacement is a JSON unicode escape, so the parsed value is
#: unchanged while the transported text can never close the element.
_SCRIPT_ESCAPES = {
    "&": "\\u0026",
    "<": "\\u003c",
    ">": "\\u003e",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}


def _escape_json_for_script(payload: str) -> str:
    """Make a JSON string safe inside a script element.

    ``json.dumps`` is called with ``ensure_ascii=True`` so the payload is pure
    ASCII and cannot depend on the host page's declared encoding. The remaining
    risk is a label that contains a closing tag, so every angle bracket and
    ampersand becomes a JSON unicode escape. The result still parses as the
    same JSON value.
    """
    for character, escape in _SCRIPT_ESCAPES.items():
        payload = payload.replace(character, escape)
    return payload


def data_payload(
    diagram: Diagram,
    *,
    model_id: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    """Return the JSON body a host serves to a ``data="url"`` page.

    This is the whole contract between a host and a linked page: the models as
    the runtime consumes them, which one to open, and an opaque ``revision``
    that changes whenever the source does. A host that re-reads the YAML file
    per request is what makes an edit visible in an open browser.
    """
    body: dict[str, Any] = {
        "generator": GENERATOR,
        "defaultModel": _select_model(diagram, model_id).id,
        "models": [model.to_payload() for model in diagram.models],
    }
    if revision is not None:
        body["revision"] = revision
    return body


def _payload(
    diagram: Diagram,
    *,
    instance: str,
    output: str,
    theme_name: str,
    default_model: str,
    levels: str,
    strings: Mapping[str, str],
    source: Mapping[str, Any] | None = None,
) -> str:
    data: dict[str, Any] = {
        "generator": GENERATOR,
        "instance": instance,
        "output": output,
        "theme": theme_name,
        "levels": levels,
        "hashKey": "model" if output == "document" else instance,
        "defaultModel": default_model,
        "layout": dict(LAYOUT_OPTIONS),
        "strings": dict(strings),
    }
    if source is None:
        data["models"] = [model.to_payload() for model in diagram.models]
    else:
        # The graph is deliberately absent: whatever is embedded here would be
        # a stale copy the moment the YAML file is saved again.
        data["source"] = dict(source)
    return _escape_json_for_script(
        json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    )


def _scheme_blocks(selector: str, dark: Mapping[str, str]) -> str:
    """Return the two dark blocks that follow a light declaration.

    The media block excludes a pinned light instance, and the attribute block
    comes last so a pinned dark instance wins on a light machine. Both carry
    the same specificity, so their order is what decides, not a weight trick.
    """
    if not dark:
        return ""
    variables = theme_css_variables(dark)
    return (
        "\n@media (prefers-color-scheme: dark) {\n"
        f'  {selector}:not([data-fy-scheme="light"]) {{\n{variables}\n  }}\n'
        "}\n"
        f'\n{selector}[data-fy-scheme="dark"] {{\n{variables}\n}}\n'
    )


def _instance_css(
    instance: str, tokens: Mapping[str, str], dark: Mapping[str, str]
) -> str:
    root_selector = "#" + instance
    variables = theme_css_variables(tokens)
    sheet = read_asset("styles.css").replace(_ROOT_PLACEHOLDER, root_selector)
    scheme = _scheme_blocks(root_selector, dark)
    return f"{root_selector} {{\n{variables}\n}}\n{scheme}\n{sheet}"


def _document_css(tokens: Mapping[str, str], dark: Mapping[str, str]) -> str:
    """Style the page around the mount, which the instance sheet cannot reach.

    The instance keys its scheme off its own root; ``body`` sits outside it, so
    the document rules key off ``<html>``, which carries the same attribute in
    document output.
    """
    body_light = (
        "body {\n"
        "  margin: 0;\n"
        f"  background: {tokens['canvas']};\n"
        f"  color: {tokens['ink']};\n"
        f"  font-family: {tokens['font-sans']};\n"
        "}\n"
    )
    body_dark = ""
    if dark:
        canvas = dark.get("canvas", tokens["canvas"])
        ink = dark.get("ink", tokens["ink"])
        body_dark = (
            "@media (prefers-color-scheme: dark) {\n"
            '  html:not([data-fy-scheme="light"]) body {\n'
            f"    background: {canvas};\n"
            f"    color: {ink};\n"
            "  }\n"
            "}\n"
            'html[data-fy-scheme="dark"] body {\n'
            f"  background: {canvas};\n"
            f"  color: {ink};\n"
            "}\n"
        )
    return (
        "html, body { height: 100%; }\n"
        + body_light
        + body_dark
        # Print is one palette in both schemes: the instance sheet repoints its
        # own tokens for print, and the page behind it goes white.
        + "@media print {\n"
        "  html, body { height: auto; background: #ffffff; color: #000000; }\n"
        "}\n"
    )


def _script_asset(name: str, data_id: str) -> str:
    source = read_asset(name)
    if "</script" in source or "<!--" in source:  # pragma: no cover - guard
        raise FlowYAMLOptionError(f"the bundled asset {name} contains an unsafe token")
    return source.replace(_DATA_PLACEHOLDER, data_id)


def _runtime_js(data_id: str) -> str:
    return _script_asset("runtime.js", data_id)


def _live_js(data_id: str) -> str:
    """The linked-source loader, emitted for ``data="url"`` only."""
    return _script_asset("live.js", data_id)


def _elk_js() -> str:
    """Return the vendored ELK bundle guarded against double evaluation."""
    bundle = read_asset("elk.bundled.js")
    return (
        "/* elkjs 0.9.3 (Eclipse Public License 2.0) vendored by FlowYAML. */\n"
        "if (typeof window.ELK === \"undefined\") {\n"
        f"{bundle}\n"
        "}\n"
    )


#: A BCP 47 tag is letters and digits in hyphen-separated subtags. The value
#: lands in an HTML attribute, so anything else is refused rather than escaped
#: into something that is not a language tag at all.
_LANG_PATTERN = re.compile(r"^[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*$")


def _checked_scheme(scheme: str) -> str:
    if scheme not in SCHEMES:
        raise FlowYAMLOptionError(
            f"unknown scheme {scheme!r}; accepted: {', '.join(SCHEMES)}"
        )
    return scheme


def _checked_levels(levels: str) -> str:
    if levels not in LEVEL_MODES:
        raise FlowYAMLOptionError(
            f"unknown levels mode {levels!r}; accepted: {', '.join(LEVEL_MODES)}"
        )
    return levels


def _checked_lang(lang: Any) -> str:
    if not isinstance(lang, str) or not lang.strip():
        raise FlowYAMLOptionError("lang must be a non-empty string, for example 'pt-BR'")
    tag = lang.strip()
    if not _LANG_PATTERN.match(tag):
        raise FlowYAMLOptionError(
            f"lang {lang!r} is not a language tag; expected something like "
            "'en', 'pt-BR' or 'zh-Hant'"
        )
    return tag


def _merged_strings(strings: Mapping[str, str] | None) -> Mapping[str, str]:
    """Return the UI string table with ``strings`` merged over it."""
    if strings is None:
        return UI_STRINGS
    if not isinstance(strings, Mapping):
        raise FlowYAMLOptionError(
            f"strings must be a mapping of UI keys to text, not "
            f"{type(strings).__name__}"
        )
    unknown = [key for key in strings if key not in UI_STRINGS]
    if unknown:
        raise FlowYAMLOptionError(
            f"unknown string key(s) {', '.join(repr(key) for key in sorted(unknown))}; "
            f"accepted: {', '.join(sorted(UI_STRINGS))}"
        )
    merged = dict(UI_STRINGS)
    for key, value in strings.items():
        if not isinstance(value, str) or not value.strip():
            raise FlowYAMLOptionError(
                f"string {key!r} must be non-empty text, found "
                f"{type(value).__name__}"
            )
        merged[key] = value
    return merged


def _validate_options(output: str, assets: str, instance_id: str | None) -> None:
    if output not in OUTPUT_MODES:
        raise FlowYAMLOptionError(
            f"unknown output {output!r}; v0 accepts {', '.join(OUTPUT_MODES)}"
        )
    if assets not in ASSET_MODES:
        raise FlowYAMLOptionError(
            f"unsupported assets mode {assets!r}; v0 implements "
            f"{', '.join(ASSET_MODES)} only"
        )
    if instance_id is not None and not _INSTANCE_PATTERN.match(instance_id):
        raise FlowYAMLOptionError(
            f"instance_id {instance_id!r} must start with a letter and contain "
            "only letters, digits, hyphen or underscore"
        )


#: Space, quote, apostrophe, angle brackets and backslash. None of them belong
#: in a URL, and each of them is a way out of the attribute or script context
#: the URL is written into.
_UNSAFE_URL_CHARACTERS = frozenset(' "<>' + chr(39) + chr(92))


def _checked_url(value: Any, option: str) -> str:
    """Return ``value`` as a URL the generated page may fetch.

    A relative URL is the normal case. An absolute one must name ``http`` or
    ``https``: a render option is not a place from which to point a page at a
    ``javascript:`` or ``data:`` target.
    """
    if not isinstance(value, str) or not value.strip():
        raise FlowYAMLOptionError(f"{option} must be a non-empty string")
    url = value.strip()
    for character in url:
        if character in _UNSAFE_URL_CHARACTERS or ord(character) < 0x20 or ord(character) == 0x7F:
            raise FlowYAMLOptionError(
                f"{option} {value!r} contains a character that is not URL safe"
            )
    match = _SCHEME_PATTERN.match(url)
    if match and match.group(1).lower() not in _ALLOWED_URL_SCHEMES:
        raise FlowYAMLOptionError(
            f"{option} {value!r} must be relative or use "
            f"{' or '.join(_ALLOWED_URL_SCHEMES)}"
        )
    return url


def _source_config(
    data: str,
    data_url: str | None,
    revision_url: str | None,
    poll_ms: int,
) -> dict[str, Any] | None:
    """Resolve the ``data`` option group into the payload's ``source`` block."""
    if data not in DATA_MODES:
        raise FlowYAMLOptionError(
            f"unknown data mode {data!r}; accepted: {', '.join(DATA_MODES)}"
        )
    if data == "inline":
        for name, value in (("data_url", data_url), ("revision_url", revision_url)):
            if value is not None:
                raise FlowYAMLOptionError(
                    f"{name} only applies to data='url'; the inline payload is "
                    "embedded, so there is nothing to fetch"
                )
        return None

    if data_url is None:
        raise FlowYAMLOptionError(
            "data='url' needs data_url: the address the host serves the payload "
            "from, for example '/flowyaml/data.json'"
        )
    if not isinstance(poll_ms, int) or isinstance(poll_ms, bool):
        raise FlowYAMLOptionError("poll_ms must be an integer number of milliseconds")
    if poll_ms < 0 or (0 < poll_ms < MIN_POLL_MS):
        raise FlowYAMLOptionError(
            f"poll_ms must be 0 (no polling) or at least {MIN_POLL_MS}"
        )

    source: dict[str, Any] = {
        "data": _checked_url(data_url, "data_url"),
        "poll": poll_ms,
    }
    if revision_url is not None:
        source["revision"] = _checked_url(revision_url, "revision_url")
    return source


def _meta_lang(model: Any) -> str:
    """Return ``meta.lang`` from the opening model, or the default.

    A flow written in Portuguese stays Portuguese for whoever renders it, which
    is why the tag belongs beside ``name`` and ``description`` in the source
    rather than only in the caller's hands.
    """
    declared = model.meta.get("lang")
    if isinstance(declared, str) and declared.strip():
        return declared
    return DEFAULT_LANG


def _select_model(diagram: Diagram, model_id: str | None) -> Any:
    if model_id is None:
        return diagram.default_model
    found = diagram.get(model_id)
    if found is None:
        raise FlowYAMLModelError(
            f"model {model_id!r} is not in this source; available models: "
            f"{', '.join(diagram.model_ids)}"
        )
    return found


def render_diagram(
    diagram: Diagram,
    *,
    model_id: str | None = None,
    output: str = "document",
    assets: str = "inline",
    data: str = "inline",
    data_url: str | None = None,
    revision_url: str | None = None,
    poll_ms: int = DEFAULT_POLL_MS,
    theme: str = DEFAULT_THEME,
    scheme: str = DEFAULT_SCHEME,
    levels: str = DEFAULT_LEVELS,
    strings: Mapping[str, str] | None = None,
    lang: str | None = None,
    instance_id: str | None = None,
) -> str:
    """Render ``diagram`` to a complete document or an embeddable fragment."""
    _validate_options(output, assets, instance_id)
    source = _source_config(data, data_url, revision_url, poll_ms)
    tokens = get_theme(theme)
    dark = get_dark_theme(theme)
    scheme = _checked_scheme(scheme)
    levels = _checked_levels(levels)
    ui_strings = _merged_strings(strings)

    selected = _select_model(diagram, model_id)

    instance = instance_id or new_instance_id()
    data_id = f"{instance}-data"

    payload = _payload(
        diagram,
        instance=instance,
        output=output,
        theme_name=theme,
        default_model=selected.id,
        levels=levels,
        strings=ui_strings,
        source=source,
    )
    css = _instance_css(instance, tokens, dark)
    runtime = _runtime_js(data_id)
    elk = _elk_js()

    mount = (
        f'<div id="{instance}" class="fy-root" data-flowyaml="v0" '
        f'data-fy-output="{output}" data-fy-theme="{html.escape(theme, quote=True)}" '
        f'data-fy-scheme="{scheme}" data-fy-levels="{levels}"></div>'
    )
    blocks = [
        f'<script id="{data_id}" type="application/json">{payload}</script>',
        f"<script>\n{elk}</script>",
        f"<script>\n{runtime}</script>",
    ]
    if source is not None:
        blocks.append(f"<script>\n{_live_js(data_id)}</script>")

    if output == "fragment":
        return "\n".join(
            [
                f"<style>\n{css}</style>",
                mount,
                *blocks,
                "",
            ]
        )

    title = selected.title or selected.id
    description = selected.meta.get("description")
    if not isinstance(description, str) or not description.strip():
        description = f"FlowYAML rendering of {title}"

    # The render option wins; otherwise the document says what language it is
    # in, which is a property of the source and travels with it.
    document_lang = _checked_lang(lang if lang is not None else _meta_lang(selected))
    color_scheme = "light dark" if scheme == "auto" else scheme

    head = [
        "<!doctype html>",
        f'<html lang="{html.escape(document_lang, quote=True)}" '
        f'data-fy-scheme="{scheme}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="color-scheme" content="{color_scheme}">',
        f'<meta name="generator" content="{html.escape(GENERATOR, quote=True)}">',
        f'<meta name="description" content="{html.escape(description.strip(), quote=True)}">',
        f'<meta name="flowyaml-model" content="{html.escape(selected.id, quote=True)}">',
        f"<title>{html.escape(title)}</title>",
        f"<style>\n{_document_css(tokens, dark)}\n{css}</style>",
        "</head>",
        "<body>",
        mount,
        *blocks,
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(head)
