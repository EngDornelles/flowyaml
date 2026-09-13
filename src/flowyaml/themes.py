"""Themes for FlowYAML v0.

``dornelles_multitech`` is the default and, in v0, the only registered theme.
A theme is a flat token table. The renderer writes the tokens as CSS custom
properties scoped to the instance root, so every rule in ``assets/styles.css``
reads ``var(--fy-*)`` and no colour is hard coded in the stylesheet.

Each theme carries two tables: the light one, which is the theme itself, and a
dark one holding only the tokens that change. Geometry and typography are
scheme independent and are declared once. The renderer emits the light table
unconditionally and the dark table twice, once behind
``prefers-color-scheme: dark`` and once behind ``data-fy-scheme="dark"``, so a
single artifact is correct on a light machine, on a dark machine, and when a
host pins either.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .errors import FlowYAMLOptionError

__all__ = [
    "DEFAULT_THEME",
    "DEFAULT_SCHEME",
    "SCHEMES",
    "THEMES",
    "DARK_THEMES",
    "get_theme",
    "get_dark_theme",
    "theme_names",
    "theme_css_variables",
]

DEFAULT_THEME = "dornelles_multitech"

#: How a rendered artifact chooses between the two token tables. ``auto``
#: follows the reader's system setting and is the default, because the artifact
#: outlives the moment it was rendered and only the reader's machine knows.
#: ``light`` and ``dark`` pin it regardless of that setting.
SCHEMES = ("auto", "light", "dark")

DEFAULT_SCHEME = "auto"

_DORNELLES_MULTITECH: Mapping[str, str] = MappingProxyType(
    {
        # Ground and surfaces
        "canvas": "#F7F5F1",
        "surface": "#FFFFFF",
        "surface-sunken": "#F1EEE8",
        "ink": "#151B24",
        # Shell and emphasized subprocess cards
        "shell": "#202732",
        "shell-raised": "#2A313C",
        "on-shell": "#F7F5F1",
        # Support text
        "slate": "#4B5563",
        "muted": "#8A94A3",
        # Structure
        "line": "#D8D2C8",
        "line-strong": "#B9B2A6",
        # Selected / evidence hierarchy only
        "amber": "#B46D3A",
        "amber-light": "#D99A57",
        # Semantic
        "start": "#2F7D4E",
        "success": "#2F7D4E",
        "warning": "#A86716",
        "danger": "#B33A2E",
        "info": "#346A8A",
        # Geometry: the parent system caps surface radius at 8px
        "radius": "8px",
        "radius-sm": "4px",
        "radius-pill": "999px",
        "stroke": "1.25px",
        "stroke-strong": "2px",
        # Typography: system technical sans only, no network font may be used
        "font-sans": (
            "'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', "
            "Arial, 'Noto Sans', 'Liberation Sans', sans-serif"
        ),
        "font-mono": (
            "ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Consolas, "
            "'DejaVu Sans Mono', monospace"
        ),
        "font-size": "13px",
        "font-size-sm": "11px",
        "font-size-chip": "11px",
        "line-height": "1.35",
        # Focus
        "focus": "#B46D3A",
        "focus-width": "2px",
        "focus-offset": "2px",
    }
)

#: The dark counterpart of ``_DORNELLES_MULTITECH``. Only the tokens that
#: change are listed: geometry, typography and focus width are scheme
#: independent and stay in the light table alone.
#:
#: The warm neutral of the light theme is kept - the ink is an off-white with
#: the same warmth as the light canvas, and amber remains the accent, lifted
#: until it carries on a dark surface. ``shell`` inverts its role: in light it
#: is the dark card that stands out, in dark it is a raised surface above the
#: canvas rather than below it.
_DORNELLES_MULTITECH_DARK: Mapping[str, str] = MappingProxyType(
    {
        # Ground and surfaces
        "canvas": "#15181D",
        "surface": "#1D2127",
        "surface-sunken": "#101317",
        "ink": "#ECE7DF",
        # Shell and emphasized subprocess cards, raised above the canvas
        "shell": "#2A2F38",
        "shell-raised": "#353B45",
        "on-shell": "#F2EDE4",
        # Support text, both at or above 4.5:1 on canvas and on surface
        "slate": "#A8B0BC",
        "muted": "#8791A0",
        # Structure. line-strong carries 3:1 on the canvas, so a border that
        # means something stays visible.
        "line": "#2E343D",
        "line-strong": "#5C6672",
        # Selected / evidence hierarchy only
        "amber": "#D9A066",
        "amber-light": "#E9BE8B",
        # Semantic
        "start": "#5FB585",
        "success": "#5FB585",
        "warning": "#D9A441",
        "danger": "#E2766A",
        "info": "#6FA8C9",
        # Focus
        "focus": "#D9A066",
    }
)

THEMES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {DEFAULT_THEME: _DORNELLES_MULTITECH}
)

#: Dark overrides per registered theme. A theme absent from this table renders
#: its light tokens in both schemes rather than guessing a dark palette.
DARK_THEMES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {DEFAULT_THEME: _DORNELLES_MULTITECH_DARK}
)


def theme_names() -> tuple[str, ...]:
    """Names of every registered theme."""
    return tuple(THEMES)


def get_theme(name: str | None = None) -> Mapping[str, str]:
    """Return the token table for ``name``.

    Raises :class:`FlowYAMLOptionError` for an unknown theme so a typo fails
    loudly instead of silently falling back to the default.
    """
    resolved = name or DEFAULT_THEME
    try:
        return THEMES[resolved]
    except KeyError:
        raise FlowYAMLOptionError(
            f"unknown theme {resolved!r}; v0 registers {', '.join(theme_names())}"
        ) from None


def get_dark_theme(name: str | None = None) -> Mapping[str, str]:
    """Return the dark overrides for ``name``.

    The name is resolved through :func:`get_theme` first, so an unknown theme
    fails the same way here as it does anywhere else. A registered theme with
    no dark table returns an empty mapping, which the renderer reads as "this
    theme looks the same in both schemes".
    """
    resolved = name or DEFAULT_THEME
    get_theme(resolved)
    return DARK_THEMES.get(resolved, MappingProxyType({}))


def theme_css_variables(tokens: Mapping[str, str]) -> str:
    """Render a token table as CSS custom property declarations."""
    return "\n".join(f"  --fy-{key}: {value};" for key, value in tokens.items())
