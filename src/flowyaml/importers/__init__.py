"""Importers that translate foreign flow notations into FlowYAML v0.

Every importer produces the package's own validated model. It never invents a
node type outside :data:`flowyaml.NODE_TYPES`, never writes geometry, and
never returns a graph that would fail :func:`flowyaml.validate`.
"""

from __future__ import annotations

from .bpmn import BPMN_SUFFIXES, read_bpmn
from .mermaid import MERMAID_SUFFIXES, read_mermaid

__all__ = ["read_mermaid", "read_bpmn", "MERMAID_SUFFIXES", "BPMN_SUFFIXES"]
