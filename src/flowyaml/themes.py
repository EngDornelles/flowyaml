"""Themes for FlowYAML v0.

``dornelles_multitech`` is the default and, in v0, the only registered theme.
A theme is a flat token table. The renderer writes the tokens as CSS custom
properties scoped to the instance root, so every rule in ``assets/styles.css``
reads ``var(--fy-*)`` and no colour is hard coded in the stylesheet.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .errors import FlowYAMLOptionError

__all__ = [
    "DEFAULT_THEME",
    "THEMES",
    "get_theme",
    "theme_names",
    "theme_css_variables",
]

DEFAULT_THEME = "dornelles_multitech"

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

THEMES: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {DEFAULT_THEME: _DORNELLES_MULTITECH}
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


def theme_css_variables(tokens: Mapping[str, str]) -> str:
    """Render a token table as CSS custom property declarations."""
    return "\n".join(f"  --fy-{key}: {value};" for key, value in tokens.items())
