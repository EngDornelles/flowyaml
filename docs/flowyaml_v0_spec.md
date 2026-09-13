# FlowYAML v0 Implementation Specification

**Status:** implementation brief, derived from read-only inspection of the delivered ERP DINFRA flowchart application on 2026-08-30.

## Purpose

FlowYAML is a callable Python renderer for YAML-defined process flows. Given valid FlowYAML YAML, it produces either:

- a complete, self-sufficient, single-page HTML document; or
- a self-contained embeddable HTML/CSS/JS fragment for a host DOM application.

The generated artifact renders in a browser without a Python process, server, npm build, or network access when using v0's required `assets="inline"` mode.

v0 is a renderer, not an editor. It must reproduce the useful behavior of the delivered ERP DINFRA flowchart application while removing its Django dependency.

## Proven source behavior

The ERP DINFRA app uses one multi-document YAML source, one graph per document. It supports the following model features:

- `meta.id`, `meta.name`, `meta.version`, and optional contextual metadata;
- nodes with stable IDs and the types `startEvent`, `endEvent`, `intermediateEvent`, `gateway`, `subprocess`, `state`, and `task`;
- directed edges with optional `tag`, detailed `label`, `kind`, and `style`;
- ELK.js layered layout, `RIGHT` direction, and orthogonal edge routing;
- rounded event nodes, diamond gateways, process cards, dashed state cards, and emphasized clickable subprocess cards;
- compact edge-label chips, with hover tooltips when an edge's full label differs from its tag;
- a tooltip for detailed state text;
- pointer-drag pan and cursor-centred wheel zoom;
- one model level at a time, with a subprocess opening its referenced model.

The ERP implementation obtains the YAML through a Django JSON endpoint and loads ELK from a vendored file. FlowYAML must retain the behavior, but embed both graph data and the vendored runtime in standalone output.

## Public API

```python
from flowyaml import render, render_file, validate, write_html

html = render(
    yaml_text,
    model_id="distribution",
    output="document",
    assets="inline",
    theme="dornelles_multitech",
)

write_html(yaml_text, "distribution.html")
errors = validate(yaml_text)
```

### Required v0 behavior

- `render(source, *, model_id=None, output="document", assets="inline", theme="dornelles_multitech") -> str`
- `render_file(path, **options) -> str`
- `write_html(source_or_path, destination, **options) -> Path`
- `validate(source) -> tuple[ValidationIssue, ...]`; rendering raises `FlowYAMLValidationError` if issues exist.
- When `model_id` is omitted, render the first YAML document. A document may select any embedded model by its `meta.id`.
- `output="document"` emits `<!doctype html>`, metadata, style, data, runtime, and the diagram mount point.
- `output="fragment"` emits an instance-scoped mount point plus scoped CSS and JS. It must not assume global IDs, document-level body styles, or a server route.
- `assets="inline"` is the only implemented v0 asset mode. The option boundary remains explicit so a future `assets="url"` mode can reference the same vendored asset from an approved URL.

## YAML contract

Input is a UTF-8 YAML string or file. A source may contain one or more documents separated by `---`.

```yaml
meta:
  id: procurement
  name: Procurement decision flow
  version: "1.0.0"
  date: "2026-08-30"

nodes:
  - id: start
    type: startEvent
    label: Request received
  - id: review
    type: task
    label: Review documentation
  - id: decision
    type: gateway
    label: Documentation complete?
  - id: archive
    type: subprocess
    label: Archive and publish
    ref: archive_flow
  - id: end
    type: endEvent
    label: Process closed

edges:
  - from: start
    to: review
  - from: review
    to: decision
  - from: decision
    to: archive
    tag: Yes
    label: Documentation is complete and can be archived.
  - from: decision
    to: end
    tag: No
```

`actors` and non-rendering metadata may be accepted and preserved for forward compatibility, but v0 does not render swimlanes or actor columns.

### Validation rules

- Each nonempty YAML document requires `meta.id`, a nonempty `nodes` list, and an `edges` list.
- Model IDs and node IDs are unique in their scopes.
- Every node requires a supported `type` and a string label; labels may be empty only for gateways used purely as merges.
- Every edge has `from` and `to`, and both references resolve in the same model.
- Self-loops are invalid in v0.
- `subprocess.ref`, if present, must refer to an embedded model ID. A subprocess without a reference is rendered as a destination, not a control.
- `kind: association` or `style: dotted` renders a dotted association edge. Other values are rejected until explicitly introduced.
- Input errors identify the model, offending field, and, where available, YAML source position.

## Render model and navigation

The engine normalizes all documents into an immutable graph model, embeds that model as escaped JSON, and invokes the browser renderer.

Each document is one level. Selecting a `subprocess` does not load a server route; it switches the active embedded model in the same HTML document. The active model is reflected in the URL hash, so browser Back/Forward works without network access. This is the standalone equivalent of the ERP app's next-level navigation.

## Layout and browser runtime

- Vendor the ELK browser bundle as package data; the observed ERP bundle is a UMD `ELK` runtime of approximately 1.6 MB.
- Use `elk.algorithm=layered`, `elk.direction=RIGHT`, orthogonal routing, `NETWORK_SIMPLEX` placement, and the proven spacing/padding defaults from the ERP app.
- Compute sizing in the browser from wrapped labels, then run ELK there. This preserves browser-font geometry and keeps Python free of a JS layout dependency.
- Use SVG for nodes, edges, arrow markers, labels, and focusable subprocess controls.
- Use unique instance prefixes for DOM IDs, SVG marker IDs, CSS class roots, event listeners, and stored navigation state.
- Fit the graph to its viewport initially. Support pointer-drag panning and cursor-centred wheel zoom constrained to 0.2–2.6x.
- Render HTML text through DOM APIs or escaped text only. YAML labels must never become `innerHTML`.

## Dornelles Multitech theme

`dornelles_multitech` is the v0 default theme. It is a Work Utilities expression of the parent B+D baseline:

- canvas `#F7F5F1`; surface `#FFFFFF`; ink `#151B24`;
- shell and emphasized subprocess cards `#202732` / `#2A313C`;
- slate support `#4B5563` and muted labels `#8A94A3`;
- structure line `#D8D2C8`;
- amber `#B46D3A` and light amber `#D99A57` only for selected/evidence hierarchy;
- semantic start/success `#2F7D4E`, warning `#A86716`, danger/end `#B33A2E`, info `#346A8A`.

The artifact must preserve the parent system's compact geometry, technical sans typography, visible focus state, low-radius surfaces (maximum 8 px), non-color-only meaning, and print legibility. It must not inherit ERP DINFRA's institutional navy/gold visual identity.

## Explicit exclusions

v0 does not include a graph editor, drag-to-reposition nodes, notebook widgets, a Python UI server, database persistence, collaboration, authentication, BPMN compliance, swimlanes, Gantt rendering, maps, export buttons, or remote asset loading.

## Implementation acceptance criteria

1. The ERP DINFRA YAML source renders without mutation and without unresolved references.
2. A generated inline HTML document renders offline in a modern browser with no network request.
3. All seven observed node types, association/dotted edges, labels, and detailed tooltips render correctly.
4. A subprocess switches to its referenced embedded model; invalid or absent references are harmless and visible as a non-clickable destination card.
5. Pan, zoom, keyboard subprocess activation, and visible focus state work on desktop and touch-capable browsers.
6. Invalid YAML produces structured Python validation errors rather than malformed output.
7. Fragment output mounts twice in one host page without identifier collisions or CSS leakage beyond its mount root.
8. Tests cover parsing/validation, normalization, HTML asset completeness, and headless-browser smoke behavior.

## Required implementation sequence

1. Package scaffold, public types, bundled-asset mechanism, and test harness.
2. YAML loader, multi-document normalization, and validation errors.
3. Standalone document renderer with embedded graph data and inline ELK bundle.
4. SVG runtime and DORNELLES MULTITECH theme, matching the observed ERP functionality.
5. In-document subprocess navigation, tooltip, pan/zoom, accessibility, and fragment mode.
6. Fixtures, offline browser checks, documentation, CLI, and release-readiness audit.


## Addendum: the v0 import layer

This brief describes the renderer. The v0 package additionally reads two
foreign notations into the same validated model, through
`flowyaml.read_mermaid` and `flowyaml.read_bpmn`.

The import layer does not widen anything the brief above states. It produces
the document shape defined in the YAML contract, passes it through the same
loader and validator, and refuses whatever it cannot map. In particular it
writes no layout, geometry or `ui` metadata: BPMN diagram interchange is read
past, and Mermaid has none to carry.

`docs/import_reference.md` holds the mapping tables and the parsing
boundaries.


## Addendum: the YAML-linked update path

The brief above describes an artifact that embeds its graph. That artifact is
a snapshot, which is exactly right for a deliverable and wrong for a source
still being edited. The v0 package therefore carries a second data mode,
which changes nothing above.

- `data="inline"` remains the default and the whole of the brief: the graph is
  embedded, the artifact is offline, `assets="inline"` still governs the
  vendored bundle, and acceptance criterion 2 (a generated inline document
  renders offline with no network request) stands unchanged and is still
  enforced by `tests/test_offline_assets.py` and `tests/test_browser.py`.
- `data="url"` leaves the graph out of the page and fetches it from
  `data_url`, so the page shows the YAML file as it stands rather than as it
  stood. The loader that performs that fetch is a separate asset emitted only
  in this mode, so the inline artifact contains no network primitive at all.
- `flowyaml.payload` is the host contract, and `flowyaml.serve` is a stdlib
  host that re-reads and re-validates the source per request. This mirrors the
  proven source behavior in `flowcharts/views.py` of ERP DINFRA, where the
  page fetches `/flowcharts/data.json` and the view re-reads the YAML file.

This is a rendering mode, not the editor excluded above: FlowYAML still draws
YAML it is given, and the YAML is still edited elsewhere. `docs/live_updates.md`
holds the mechanism, the browser limits and the operational boundaries.
