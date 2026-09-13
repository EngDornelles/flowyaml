"""FlowYAML: a callable Python renderer for YAML-defined process flows.

Given valid FlowYAML YAML, the package produces either a complete self
sufficient single page HTML document or a self contained embeddable fragment.
The generated artifact renders in a browser with no Python process, no server,
no npm build and no network access.

That artifact is a snapshot: it shows the YAML as it stood when it was
written. When the YAML is still being edited, ``data="url"`` renders the same
page with its graph left out and fetched from a host instead, and
``flowyaml.serve`` is a stdlib host that re-reads the file per request. See
``docs/live_updates.md``.

v0 is a renderer, not an editor.
"""

from __future__ import annotations

from typing import Any

from ._version import __version__
from .api import (
    load,
    models,
    payload,
    payload_json,
    read_bpmn,
    read_mermaid,
    read_source,
    render,
    render_file,
    to_yaml,
    validate,
    write_html,
)
from .errors import (
    FlowYAMLError,
    FlowYAMLImportError,
    FlowYAMLModelError,
    FlowYAMLOptionError,
    FlowYAMLValidationError,
    ValidationIssue,
)
from .model import (
    CLICKABLE_NODE_TYPES,
    EDGE_KINDS,
    EDGE_STYLES,
    NODE_TYPES,
    Diagram,
    Edge,
    Model,
    Node,
)
from .renderer import (
    ASSET_MODES,
    DATA_MODES,
    DEFAULT_LANG,
    DEFAULT_LEVELS,
    DEFAULT_POLL_MS,
    LAYOUT_OPTIONS,
    LEVEL_MODES,
    OUTPUT_MODES,
    UI_STRINGS,
)
from .themes import (
    DARK_THEMES,
    DEFAULT_SCHEME,
    DEFAULT_THEME,
    SCHEMES,
    THEMES,
    theme_names,
)

__all__ = [
    "__version__",
    # public API
    "render",
    "render_file",
    "write_html",
    "validate",
    "load",
    "models",
    "payload",
    "payload_json",
    "read_source",
    "to_yaml",
    # live host (imported on first use)
    "serve",
    "create_server",
    "LinkedSource",
    # importers
    "read_mermaid",
    "read_bpmn",
    # errors
    "ValidationIssue",
    "FlowYAMLError",
    "FlowYAMLValidationError",
    "FlowYAMLModelError",
    "FlowYAMLOptionError",
    "FlowYAMLImportError",
    # model
    "Diagram",
    "Model",
    "Node",
    "Edge",
    "NODE_TYPES",
    "EDGE_KINDS",
    "EDGE_STYLES",
    "CLICKABLE_NODE_TYPES",
    # options
    "OUTPUT_MODES",
    "ASSET_MODES",
    "DATA_MODES",
    "LEVEL_MODES",
    "DEFAULT_LEVELS",
    "DEFAULT_LANG",
    "DEFAULT_POLL_MS",
    "LAYOUT_OPTIONS",
    "UI_STRINGS",
    "SCHEMES",
    "DEFAULT_SCHEME",
    "DEFAULT_THEME",
    "THEMES",
    "DARK_THEMES",
    "theme_names",
]

#: The live host is the one part of the package that needs a socket. Importing
#: it on demand keeps ``import flowyaml`` a pure renderer import.
_LIVE_EXPORTS = frozenset({"serve", "create_server", "LinkedSource"})


def __getattr__(name: str) -> Any:
    if name in _LIVE_EXPORTS:
        from . import live

        return getattr(live, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
