"""The FlowYAML v0 public API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .errors import FlowYAMLValidationError, ValidationIssue
from .importers import read_bpmn, read_mermaid
from .model import Diagram
from .renderer import (
    DEFAULT_LEVELS,
    DEFAULT_POLL_MS,
    data_payload,
    render_diagram,
)
from .serialize import to_yaml as _diagram_to_yaml
from .themes import DEFAULT_SCHEME, DEFAULT_THEME
from .validation import build

__all__ = [
    "render",
    "render_file",
    "write_html",
    "validate",
    "load",
    "models",
    "payload",
    "payload_json",
    "read_source",
    "read_mermaid",
    "read_bpmn",
    "to_yaml",
]

_YAML_SUFFIXES = (".yaml", ".yml", ".flowyaml")


def read_source(source: str | os.PathLike[str]) -> str:
    """Return YAML text for ``source``.

    A :class:`~pathlib.Path` is always read from disk. A ``str`` is treated as
    YAML text unless it is a single line with a YAML suffix that exists on
    disk, which keeps ``write_html("flow.yaml", ...)`` convenient without ever
    guessing about real YAML content.
    """
    if isinstance(source, Path) or (
        isinstance(source, os.PathLike) and not isinstance(source, str)
    ):
        return Path(source).read_text(encoding="utf-8")
    if isinstance(source, str):
        looks_like_path = (
            "\n" not in source
            and len(source) < 4096
            and source.strip().lower().endswith(_YAML_SUFFIXES)
        )
        if looks_like_path:
            candidate = Path(source)
            try:
                if candidate.is_file():
                    return candidate.read_text(encoding="utf-8")
            except OSError:  # pragma: no cover - unusual filesystem states
                pass
        return source
    raise TypeError(f"source must be str or PathLike, not {type(source).__name__}")


def validate(source: str | os.PathLike[str] | Diagram) -> tuple[ValidationIssue, ...]:
    """Return every structured issue found in ``source``.

    An empty tuple means the source is renderable. A :class:`Diagram` is
    already normalized, so it reports nothing.
    """
    if isinstance(source, Diagram):
        return ()
    return build(read_source(source))[1]


def load(source: str | os.PathLike[str] | Diagram) -> Diagram:
    """Parse and validate ``source`` into the immutable graph model.

    A :class:`Diagram` passes straight through, which is what lets an
    importer's result be handed to :func:`render` and :func:`write_html`
    without a YAML round trip.
    """
    if isinstance(source, Diagram):
        return source
    diagram, issues = build(read_source(source))
    if issues or diagram is None:
        raise FlowYAMLValidationError(issues)
    return diagram


def models(source: str | os.PathLike[str] | Diagram) -> tuple[str, ...]:
    """Return the ``meta.id`` of every model in ``source``, in document order."""
    return load(source).model_ids


def to_yaml(source: str | os.PathLike[str] | Diagram) -> str:
    """Return canonical FlowYAML YAML for ``source``.

    Given an imported diagram this is the round trip back to editable source
    text, so a Mermaid or BPMN file can become a FlowYAML file on disk. The
    output never carries geometry: FlowYAML lays a graph out in the browser.
    """
    return _diagram_to_yaml(load(source))


def payload(
    source: str | os.PathLike[str] | Diagram,
    *,
    model_id: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    """Return the JSON body a host serves to a ``data="url"`` page.

    This is the FlowYAML counterpart of the ERP DINFRA ``data.json`` view: the
    host re-reads the YAML file, calls this, and answers with the result, so a
    saved edit is visible on the next request. ``revision`` is any opaque
    marker that changes when the source does - a content digest, an mtime, a
    commit id. The page polls for it and reloads the graph when it moves.
    """
    return data_payload(load(source), model_id=model_id, revision=revision)


def payload_json(
    source: str | os.PathLike[str] | Diagram,
    *,
    model_id: str | None = None,
    revision: str | None = None,
) -> str:
    """Return :func:`payload` serialized as compact UTF-8-safe JSON."""
    return json.dumps(
        payload(source, model_id=model_id, revision=revision),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render(
    source: str | os.PathLike[str] | Diagram,
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
    """Render ``source`` to self-sufficient HTML.

    Parameters
    ----------
    source:
        YAML text, a path to a YAML file, or a :class:`Diagram` such as the
        one :func:`read_mermaid` and :func:`read_bpmn` return.
    model_id:
        Which embedded model opens first. Defaults to the first document.
        Every model stays embedded regardless, so subprocess navigation works.
    output:
        ``"document"`` for a complete page, ``"fragment"`` for a host-safe
        block that can be mounted more than once on one page.
    assets:
        ``"inline"`` only in v0.
    data:
        ``"inline"`` embeds the graph once; the artifact is then complete and
        offline, and it never sees a later edit of the YAML. ``"url"`` leaves
        the graph out and has the page fetch it from ``data_url``, so an edited
        YAML file reaches the page on reload, and within ``poll_ms`` without
        one. A ``"url"`` page needs an http host: browsers refuse the fetch
        when the page itself was opened over ``file://``.
    data_url:
        Where the host serves :func:`payload`. Required for ``data="url"``,
        rejected otherwise. Relative, or absolute http(s).
    revision_url:
        Optional cheaper poll target answering ``{"revision": ...}``. Without
        it the page polls ``data_url`` itself and compares revisions.
    poll_ms:
        How often a ``"url"`` page checks for a new revision. ``0`` polls
        never, which is the ERP DINFRA behaviour: an edit shows up on reload.
    theme:
        Registered theme name. Defaults to ``dornelles_multitech``.
    scheme:
        ``"auto"`` follows the reader's system setting, which is the default
        because the artifact outlives the moment it was rendered. ``"light"``
        and ``"dark"`` pin it. Both palettes are emitted either way, so no
        choice here costs the other one.
    levels:
        How the page shows where the reader is. ``"breadcrumb"`` is the
        horizontal trail in the toolbar. ``"snapshot"`` replaces it with a
        stripe of the levels above, the nearest carrying a picture of the
        diagram the reader came from, plus a level counter. The stripe spends
        vertical room, so a flow that is taller than it is wide wants the
        breadcrumb.
    strings:
        Overrides for the UI text the runtime writes itself - buttons, the
        canvas hint, screen-reader labels and failure messages. Merged over the
        defaults, so one key can be replaced without restating the rest, and an
        unknown key is rejected rather than ignored. This is where a diagram
        written in another language, or in another vocabulary than BPMN's, gets
        furniture that matches it.
    lang:
        The document's language tag. Defaults to ``meta.lang`` from the opening
        model, then to ``"en"``. Document output only; a fragment inherits the
        host page's language.
    instance_id:
        Fixed DOM prefix. Omit it for a fresh random prefix per render, which
        is what keeps two fragments on one page from colliding.

    Raises
    ------
    FlowYAMLValidationError
        If the source has any validation issue.
    FlowYAMLModelError
        If ``model_id`` is not present in the source.
    FlowYAMLOptionError
        For an unsupported ``output``, ``assets``, ``theme``, ``scheme``,
        ``levels``, ``strings``, ``lang`` or ``instance_id``.
    """
    diagram = load(source)
    return render_diagram(
        diagram,
        model_id=model_id,
        output=output,
        assets=assets,
        data=data,
        data_url=data_url,
        revision_url=revision_url,
        poll_ms=poll_ms,
        theme=theme,
        scheme=scheme,
        levels=levels,
        strings=strings,
        lang=lang,
        instance_id=instance_id,
    )


def render_file(path: str | os.PathLike[str], **options: Any) -> str:
    """Render the YAML file at ``path``."""
    return render(Path(path).read_text(encoding="utf-8"), **options)


def write_html(
    source_or_path: str | os.PathLike[str] | Diagram,
    destination: str | os.PathLike[str],
    **options: Any,
) -> Path:
    """Render ``source_or_path`` and write it to ``destination``.

    Returns the written path.
    """
    target = Path(destination)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(source_or_path, **options), encoding="utf-8")
    return target
