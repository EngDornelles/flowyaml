# FlowYAML Future-Fit Ledger

This is an intentionally non-binding parking lot. Items move into an implementation brief only after Lucas selects them.

| Surface | Candidate capability | Why it fits | Current status |
| --- | --- | --- | --- |
| `flowyaml.render` | Additional named themes | Keeps the renderer reusable while preserving a formal default | later |
| `flowyaml.render` | SVG, PNG, and PDF export | Natural artifact outputs for reports and portals | later |
| `flowyaml.render` | Reusable node templates and diagram metadata panels | Reduces repeated YAML without changing the core graph model | later |
| `flowyaml.render` | URL-backed vendored assets | Reduces generated output size where a controlled host is acceptable | later; v0 is inline only |
| `flowyaml.notebook` | Jupyter display object and interactive inspector | A notebook is a viable local host for inspection and experimentation | separate module |
| `flowyaml.notebook` | Editable graph/model workflow | Requires a browser widget or desktop host; must not contaminate the pure renderer | separate feasibility gate |
| Standalone DOM frontend | YAML editor, node inspector, templates, project browser, persistence | These are application concerns, not package-renderer concerns | separate application |
| Standalone DOM frontend | Manual layout override editor | Useful once automatic layout is proven; needs an explicit position-extension schema | later |
| Advanced graph model | Groups, swimlanes, BPMN-like semantics | Valuable for organizational flows but materially expands the schema/layout contract | later |
| `flowyaml.read_*` | Export back to Mermaid or BPMN | The importers prove the mapping is expressible; the reverse needs a lossy-direction policy first | later |
| `flowyaml.read_*` | Rendered groups for imported Mermaid subgraphs and BPMN pools | Membership is already preserved on the model; only the layout contract is missing | later; gated on the group shape |
| Advanced graph model | Gantt and map-linked views | Potential Omega/Work Utilities reuse, but not flowchart semantics | separate renderer family |

Delivered in v0 and no longer parked: Mermaid flowchart and BPMN 2.0 XML
import (`docs/import_reference.md`), and the YAML-linked update path -
`render(data="url")` plus `flowyaml.payload` and `flowyaml serve`
(`docs/live_updates.md`). The linked mode is a second rendering mode, not an
editor: it does not move the "Standalone DOM frontend" rows above.

## Rule

The v0 renderer earns expansion only after it can render valid YAML to a portable offline artifact with parity for the proven interactions it was derived from.
