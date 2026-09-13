# FlowYAML

A callable Python renderer for YAML-defined process flows.

Given valid FlowYAML YAML, the package produces either a complete
self-sufficient single-page HTML document, or a self-contained embeddable
HTML/CSS/JS fragment for a host DOM application. The generated artifact renders
in a browser with **no Python process, no server, no npm build and no network
access**.

It also reads two foreign notations, Mermaid flowcharts and BPMN 2.0 XML, into
the same validated model.

That artifact is a snapshot of the YAML as it stood when it was written. While
the YAML is still being edited, `flowyaml serve` keeps a page attached to the
file instead, so a save shows up in the open browser — the arrangement the
delivered ERP DINFRA flowchart uses. See
[Keeping the HTML linked to the YAML](docs/live_updates.md).

v0 is a renderer, not an editor.

The first public-package candidate is `0.1.0.0`. The earlier internal
`0.0.0.0` build was YAML-linked by default and did not yet provide the
standalone, self-sufficient HTML delivery mode.

## Install

```bash
pip install -e .
```

The only runtime dependency is PyYAML. The browser layout engine is vendored as
package data, so nothing is fetched at build time or at view time.

## Quick start

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

Import an existing diagram instead of writing YAML by hand:

```python
import flowyaml as fyml

graph = fyml.read_mermaid("workflow.mmd")
other = fyml.read_bpmn("process.bpmn")

fyml.write_html(graph, "workflow.html")
```

```bash
flowyaml render examples/distribution.yaml -o distribution.html
flowyaml render examples/distribution.yaml --output fragment > panel.html
flowyaml render examples/distribution.yaml --scheme dark --levels snapshot
flowyaml serve examples/distribution.yaml
flowyaml data examples/distribution.yaml -o distribution.data.json
flowyaml validate examples/distribution.yaml
flowyaml models examples/distribution.yaml
flowyaml import examples/onboarding.mmd -o onboarding.yaml
flowyaml import examples/order_handling.bpmn -o order.yaml
flowyaml themes
```

Open the written file directly from disk. Nothing else is needed.

For a complete notebook example, follow
[`examples/notebooks/quest_for_x`](examples/notebooks/quest_for_x). It starts
with a multi-document YAML model, validates every navigable level, writes a
standalone HTML artifact, and previews it in the notebook.

While you are still editing the YAML, serve it instead:

```bash
flowyaml serve examples/distribution.yaml --open
```

Edit the file, save, and the open page follows it. Nothing is rebuilt.

For notebook-kernel installation and deterministic LLM/agent invocation, see
[Notebook and agent usage](docs/notebook_and_agent_usage.md).

## Public API

| Callable | Purpose |
| --- | --- |
| `render(source, *, model_id=None, output="document", assets="inline", theme="dornelles_multitech", scheme="auto", levels="breadcrumb", strings=None, lang=None, instance_id=None) -> str` | Render YAML text or a path to HTML. |
| `render_file(path, **options) -> str` | Render the YAML file at `path`. |
| `write_html(source_or_path, destination, **options) -> Path` | Render and write; returns the written path. |
| `validate(source) -> tuple[ValidationIssue, ...]` | Structured issues; empty means renderable. |
| `load(source) -> Diagram` | The immutable normalized model. |
| `models(source) -> tuple[str, ...]` | Every `meta.id`, in document order. |
| `read_mermaid(source, *, model_id=None, name=None) -> Diagram` | Import a Mermaid flowchart. |
| `read_bpmn(source, *, model_id=None, name=None) -> Diagram` | Import a BPMN 2.0 XML process. |
| `to_yaml(source) -> str` | Canonical FlowYAML YAML for any source or diagram. |
| `payload(source, *, model_id=None, revision=None) -> dict` | The JSON body a host serves to a `data="url"` page. |
| `payload_json(source, ...) -> str` | The same body, serialized. |
| `serve(source, *, host, port, model_id, theme, poll_ms, open_browser) -> None` | Local host that re-reads the YAML per request. |

Everywhere the table says `source`, the argument may be YAML text, a path to a
YAML file, or a `Diagram` — which is what the two importers return, so an
imported graph goes straight to `render` and `write_html` with no YAML round
trip.

Rendering raises `FlowYAMLValidationError` when any issue exists,
`FlowYAMLModelError` for an unknown `model_id`, and `FlowYAMLOptionError` for an
unsupported option value. An importer raises `FlowYAMLImportError`, which
carries the format, the source name and the offending line where the position
is recoverable.

When `model_id` is omitted the first YAML document opens first. **Every** model
stays embedded either way, which is what makes subprocess navigation work
without a server.

### Options

- `output="document"` emits `<!doctype html>`, metadata, style, data, runtime
  and the diagram mount point.
- `output="fragment"` emits an instance-scoped mount point plus scoped CSS and
  JS. It assumes no global id, no document-level body style and no server route,
  and it can be mounted more than once on one page.
- `assets="inline"` is the only implemented v0 asset mode. The boundary stays
  explicit so a future `assets="url"` mode can reference the same vendored asset
  from an approved URL.
- `data="inline"` embeds the graph, which is what makes the artifact offline
  and permanent. `data="url"` leaves the graph out and has the page fetch it
  from `data_url`, so an edited YAML file reaches a page that is already open.
  `revision_url` and `poll_ms` tune how the page notices a change; `poll_ms=0`
  means it notices on reload only. A `data="url"` page needs an http host:
  browsers refuse the fetch when the page itself was opened over `file://`,
  and the page says so rather than sitting empty. See
  [docs/live_updates.md](docs/live_updates.md).
- `scheme="auto"` follows the reader's system setting and is the default;
  `"light"` and `"dark"` pin it. Both palettes are written into every artifact
  either way, so the choice decides what the page uses, not what it contains.
  A host can override a rendered page with `data-fy-scheme` on the mount.
  Printing uses one palette in both schemes.
- `levels="breadcrumb"` keeps the trail in the toolbar and is the default.
  `levels="snapshot"` replaces it with a stripe of the levels above - the
  nearest one showing a picture of the diagram the reader came from - and adds
  a level counter. The stripe buys recall with vertical room, so a flow that is
  taller than it is wide should stay on the breadcrumb.
- `strings={...}` overrides the words the runtime writes for itself: the
  buttons, the canvas hint, the screen-reader labels and the failure messages.
  It merges over the defaults, so one key replaces one key, and an unknown key
  is refused rather than quietly ignored. This is where a diagram that is not
  in English, or not in BPMN's vocabulary, gets furniture that matches it.
- `lang="pt-BR"` sets the document language, defaulting to `meta.lang` and then
  to `en`. Fragments inherit the host page instead.
- `instance_id` fixes the DOM prefix. Omit it and every render gets a fresh
  random prefix, which is what keeps two fragments from colliding. Pass it when
  you want byte-reproducible output.

A flow written in Portuguese, with furniture to match:

```python
fyml.write_html(
    "cozinha.yaml",
    "cozinha.html",
    levels="snapshot",
    strings={
        "back": "Voltar",
        "backAria": "Subir um nível",
        "fit": "Ajustar",
        "nextSteps": "Explorar os próximos passos",
        "open": "Abrir etapa",
        "hint": "Arraste para mover · role para ampliar",
    },
)
```

## YAML contract

A source is UTF-8 YAML with one or more documents separated by `---`. One
document is one flow level.

```yaml
meta:
  id: procurement
  name: Procurement decision flow
  version: "1.0.0"
  date: "2026-08-30"
  lang: en

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
    tag: "Yes"
    label: Documentation is complete and can be archived.
  - from: decision
    to: end
    tag: "No"
```

Node types: `startEvent`, `endEvent`, `intermediateEvent`, `gateway`,
`subprocess`, `state`, `task`.

Optional node key `detail` (alias `description`) becomes a hover and focus
tooltip. Optional edge keys are `tag` (the compact chip), `label` (the full
text, shown as a tooltip when it differs from the chip), `kind`
(`sequence` or `association`) and `style` (`solid` or `dotted`).

`meta.lang` is the document's language tag. It reaches `<html lang>`, which
is what decides a screen reader's voice, so it belongs with the source rather
than only with whoever renders it. `render(lang=...)` overrides it.

`actors` and other non-rendering metadata are accepted and preserved on the
model for forward compatibility. v0 does not render swimlanes or actor columns.

> Bare `Yes`, `No`, `On` and `Off` are YAML booleans, not strings. Quote them.
> FlowYAML rejects a boolean tag with a message that says so.

### Validation rules

- Each nonempty document needs `meta.id`, a nonempty `nodes` list, and an
  `edges` list (which may be empty).
- Model ids and node ids are unique in their scopes.
- Every node needs a supported `type` and a string `label`. A label may be empty
  only on the two connector shapes: a `gateway` used purely as a merge, and an
  `intermediateEvent` used purely as a junction. Every other type carries
  process meaning and needs text.
- Every edge has `from` and `to`, and both resolve inside the same model.
- Self-loops are invalid in v0.
- `subprocess.ref`, when present, must name an embedded model id. Only
  `subprocess` nodes may carry `ref`. A subprocess without a `ref` renders as a
  destination card, not a control.
- Only `kind: association` and `style: dotted` are accepted beyond the defaults.
  Anything else is rejected until it is explicitly introduced.

Each issue carries a stable `code`, a `message`, the `model_id`, the
`document_index`, the offending `field`, and the YAML `line`/`column` where the
position is recoverable.

## Importing Mermaid and BPMN

```python
import flowyaml as fyml

graph = fyml.read_mermaid("workflow.mmd")     # text or a path
other = fyml.read_bpmn("process.bpmn")        # text or a path

fyml.render(graph)                            # straight to HTML
fyml.to_yaml(other)                           # or to editable FlowYAML YAML
```

```bash
flowyaml import workflow.mmd -o workflow.yaml
flowyaml import process.bpmn --format bpmn > process.yaml
```

Two rules hold for both importers.

- **The output is always valid.** An importer builds plain FlowYAML documents
  and runs them through the same loader and validator as a hand written
  source. There is no second code path.
- **No geometry, ever.** Nothing an importer writes describes a position, a
  size or any other `ui` metadata. FlowYAML measures wrapped labels in the
  browser and runs ELK there, so a stored coordinate would only fight the
  layout engine. BPMN's whole `bpmndi:BPMNDiagram` section is read past and
  discarded.

Identifiers survive when they are safe: a Mermaid `check_stock` and a BPMN
`Activity_0x9f2c` stay exactly themselves. Only characters that would need
escaping downstream are folded to `_`, and a collision gains a deterministic
`_2` suffix.

**Mermaid.** `graph` and `flowchart` declarations with any direction; the
twelve node shapes; solid, thick, dotted and invisible links; edge text in all
four spellings; chains and `&` groups; frontmatter `title`. Subgraphs flatten
and keep their membership in a non-rendering `group` key. Styling, class and
click statements are read and discarded, because FlowYAML owns its theme.
`A([...])` and `A((...))` become a start, intermediate or end event according
to node degree, since Mermaid spells the whole event family one way.

**BPMN 2.0.** Events, the eight task kinds, the five gateways, sub-processes,
call activities, data references, text annotations, sequence flows,
associations, data associations, boundary attachments and message flows.
Elements are matched by local name, so `bpmn:`, `bpmn2:`, `semantic:` and a
default namespace all read the same. An expanded `subProcess` becomes a model
of its own and the node that held it gets the `ref` that opens it, so BPMN
nesting arrives as FlowYAML's own in-document navigation. Lanes become
`actors` and a per-node `lane` key.

Anything outside those boundaries stops with a `FlowYAMLImportError` naming
the format, the source and the line: a `sequenceDiagram`, an unclosed shape, a
self-loop, a subgraph used as an edge endpoint, an unmapped BPMN flow element,
an unresolved sequence flow, a DTD. Nothing is silently dropped that would
change the graph.

`docs/import_reference.md` carries the full mapping tables and the exact
parsing boundaries. `examples/onboarding.mmd` and
`examples/order_handling.bpmn` exercise both surfaces.

## Keeping the page linked to the YAML

A rendered artifact is a snapshot. `flowyaml serve` is the other half: a
stdlib host that answers three fixed paths and re-reads the YAML file on every
data request, so editing and saving updates the page in place.

```
/                        the page, rendered with data="url"
/flowyaml/data.json      the graph, re-read and re-validated per request
/flowyaml/revision.json  a content digest, so the page can poll cheaply
```

This is the mechanism the delivered ERP DINFRA flowchart uses, where a Django
view re-reads `dinfra_workflows.yaml` per request and the static page fetches
it. To put a linked diagram inside your own application, render the shell with
`data="url"` and serve `flowyaml.payload(...)` from your own route.

Two limits stated plainly: a browser refuses to fetch a sibling file from a
`file://` page, so a linked page opened from disk reports that instead of
pretending, and nothing in a browser watches a file, so the update is bounded
by the poll interval. `docs/live_updates.md` has the whole picture.

## Rendering and navigation

The engine normalizes every document into an immutable graph model, embeds that
model as escaped JSON, and hands it to the browser renderer.

- Layout is [elkjs](https://github.com/kieler/elkjs) with `elk.algorithm=layered`,
  `elk.direction=RIGHT`, orthogonal routing and `NETWORK_SIMPLEX` placement.
  Node sizes are measured in the browser from the wrapped label, so the geometry
  follows the real font metrics and Python carries no JS layout dependency.
- Nodes, edges, arrow markers, labels and subprocess controls are SVG.
- Selecting a `subprocess` does not load a route. It switches the active
  embedded model in the same document and writes the choice to the URL hash, so
  browser Back and Forward walk the levels with no network access.
  A standalone document uses the hash key `model`; a fragment uses its own
  instance prefix as the key, so several instances never read each other's state.
- Pointer drag pans, wheel zoom is cursor-centred, two-finger pinch zooms on
  touch, and scale is clamped to 0.2x-2.6x. The view fits the viewport on load
  and refits on resize until the reader adjusts it.

### Keyboard and accessibility

| Key | Action |
| --- | --- |
| `Tab` | Move between subprocess controls and detailed labels |
| `Enter` / `Space` | Open the focused subprocess |
| `Backspace` | Go up one level |
| Arrow keys | Pan |
| `+` / `-` | Zoom |
| `0` | Fit |
| `Escape` | Dismiss the tooltip |

Subprocess controls are `role="button"` with a visible focus ring. A node or
chip that carries `detail` folds that text into its own accessible name, so a
screen reader never has to read it from the shared tooltip element. Meaning
never depends on colour alone: the seven node types differ by shape and stroke, a
navigable subprocess carries a BPMN collapsed-marker box, a chevron underline
and a pointer cursor, and a detailed edge chip carries a `≡` glyph.

Every label reaches the DOM through `textContent`, never `innerHTML`, and the
embedded payload escapes `<`, `>` and `&` as JSON unicode escapes so no label
can close the script element.

Every output path writes UTF-8: `--out`, `write_html`, and rendering to stdout
alike. The document declares `<meta charset="utf-8">`, so the console codepage
never decides how an accented label is encoded.

## Theme

`dornelles_multitech` is the v0 default and, in v0, the only registered theme.
It is a Work Utilities expression of the parent B+D baseline: canvas `#F7F5F1`,
surface `#FFFFFF`, ink `#151B24`, shell `#202732` / `#2A313C`, slate `#4B5563`,
muted `#8A94A3`, structure line `#D8D2C8`, amber `#B46D3A` / `#D99A57` reserved
for selected and evidence hierarchy, and semantic start `#2F7D4E`, warning
`#A86716`, danger `#B33A2E`, info `#346A8A`.

It keeps the parent system's compact geometry, technical system-sans typography,
visible focus state, low-radius surfaces (8 px maximum) and print legibility. It
deliberately does not inherit ERP DINFRA's institutional navy and gold identity.

Tokens are written as `--fy-*` custom properties scoped to the instance root, so
every rule in the stylesheet reads a variable and no colour is hard coded.

## Vendored assets

`src/flowyaml/assets/elk.bundled.js` is the elkjs 0.9.3 UMD browser bundle
(~1.6 MB), redistributed under the Eclipse Public License 2.0. See
`src/flowyaml/assets/elk.LICENSE.md` and `NOTICE.md`. It runs its layout in
process; no web worker is constructed and no script is fetched. Repeated
inclusion on one page is guarded by `if (typeof window.ELK === "undefined")`, so
the bundle evaluates once however many fragments are mounted.

## Tests

```bash
python -m pytest tests -q                      # everything
python -m pytest tests -q -m "not browser"     # no browser needed
python -m pytest tests/test_browser.py -q      # headless offline checks
python -m pytest tests/test_live.py -q         # the YAML-linked update path
python -m pytest tests/test_live_browser.py -q # an open page follows an edit
```

The browser tests need `pip install playwright && playwright install chromium`
and skip cleanly when it is unavailable. They load the generated `file://`
document with an interception rule that aborts and records every request that
leaves the file scheme, so a passing run is itself the offline proof. The
non-browser suite makes the same claim statically, by asserting that the only
absolute URL FlowYAML writes is the SVG namespace.

Release preparation and the account-side Trusted Publishing gates are recorded
in [RELEASING.md](RELEASING.md).

## Not in v0

No graph editor, drag-to-reposition, notebook widget, database persistence,
collaboration, authentication, swimlane, Gantt, map, export button or remote
asset loading. See `docs/future_fit_ledger.md`.

`flowyaml serve` is a local authoring host with no authentication, three fixed
routes and no filesystem mapping; it is not a production server, and it does
not make v0 an editor. The YAML is edited in your editor.

Importing BPMN is not BPMN compliance. v0 renders seven node types, two edge
kinds and two edge styles; it has no pool boundary, no swimlane and no
execution semantics. The importer translates a BPMN file into that model and
refuses what it cannot, rather than widening the contract.

There is no export back to Mermaid or BPMN. `to_yaml` writes FlowYAML.

## License

FlowYAML is released under the [MIT License](LICENSE). The bundled, unmodified
`elkjs` layout engine remains under the Eclipse Public License 2.0; its license
and version records ship with every distribution and are summarized in
[NOTICE.md](NOTICE.md).
