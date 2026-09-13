# Keeping the HTML linked to the YAML

FlowYAML v0 renders a snapshot. `render()` embeds the whole graph in the page,
which is what makes the artifact portable, offline and durable — and also what
makes it deaf to the next edit of the YAML file. This document describes the
second mode, which keeps a page attached to its source, and is explicit about
what a browser will and will not do.

## What ERP DINFRA actually does

The delivered flowchart app in ERP DINFRA is a three-part arrangement:

| Piece | File | Role |
| --- | --- | --- |
| Source of truth | `flowcharts/sources/dinfra_workflows.yaml` | Multi-document YAML, one document per flow level |
| Host | `flowcharts/views.py` | `flowchart_data` re-reads and re-parses that file **per request** and answers `JsonResponse` |
| Page | `static/flowcharts/dinfra_map.html` | Carries no graph; `boot()` does `fetch('/flowcharts/data.json')` and lays the result out with ELK |

There is no build step and no generated copy of the graph. Editing the YAML
and reloading the browser is the entire update loop, because the page asks the
host for the data every time it boots, and the host reads the file every time
it is asked.

FlowYAML now offers the same arrangement, without requiring Django.

## The two modes

| | `data="inline"` (default) | `data="url"` |
| --- | --- | --- |
| Where the graph lives | Embedded in the page | Fetched from the host |
| Sees a later YAML edit | No | Yes |
| Needs a host | No | Yes, over http |
| Works from `file://` | Yes | No (see below) |
| Network requests | None at all | One per load, plus polling |
| Use it for | Deliverables, attachments, archives | Authoring and review while the YAML is still moving |

`data="inline"` is untouched by this work: the same bytes, the same offline
guarantees, the same tests. The linked-source loader is a separate asset
(`assets/live.js`) that is only emitted for `data="url"`, so the default
artifact contains no fetch primitive at all — `tests/test_offline_assets.py`
holds that line.

## Using it

The short path is the bundled host:

```bash
flowyaml serve examples/distribution.yaml
# flowyaml: serving examples/distribution.yaml at http://127.0.0.1:8000/
```

Open the page, edit the YAML in your editor, save. The drawing follows within
a second. Nothing is rebuilt and the page is never reloaded by hand.

Options: `--port`, `--host`, `--model`, `--theme`, `--open`, `--verbose`, and
`--poll-ms` (`--poll-ms 0` turns polling off, leaving exactly the ERP
behaviour: the edit appears when you reload the page).

From Python:

```python
import flowyaml

flowyaml.serve("flow.yaml", port=8000, open_browser=True)
```

## Hosting it inside your own application

`flowyaml serve` is a development host. To put a linked diagram inside a real
application — which is what ERP DINFRA does — render the shell yourself and
serve the payload from your own route:

```python
import flowyaml

def diagram(request):                      # the page
    return HttpResponse(flowyaml.render(
        SOURCE.read_text(encoding="utf-8"),
        data="url",
        data_url="/diagram/data.json",
        revision_url="/diagram/revision.json",   # optional, cheaper polling
        poll_ms=1000,                            # 0 for reload-only updates
    ))

def diagram_data(request):                 # the ERP flowchart_data equivalent
    raw = SOURCE.read_bytes()
    return JsonResponse(flowyaml.payload(
        raw.decode("utf-8"),
        revision=hashlib.sha256(raw).hexdigest()[:16],
    ))
```

`flowyaml.payload(source, model_id=None, revision=None)` returns the whole
contract:

```json
{"generator": "flowyaml 0.1.1.0",
 "revision": "5f73e72a3c0e0466",
 "defaultModel": "distribution",
 "models": [{"id": "...", "title": "...", "nodes": [...], "edges": [...]}]}
```

`revision` is any opaque marker that changes when the source does — a content
digest, an mtime, a commit id. The page compares it and only re-fetches the
graph when it moves. Omit `revision_url` and the page polls the data route
itself, comparing the same field.

`flowyaml data flow.yaml -o flow.data.json` writes that same body, for a host
that prefers to serve a static file it regenerates on its own schedule.

### A worked artifact

`artifacts/distribution_linked.{yaml,html,data.json}` is that arrangement in
its smallest form: a page rendered with `data_url="distribution_linked.data.json"`
and the payload next to it. Any static file server will do — no `revision_url`
is set, so the page polls the payload itself and compares the revision inside
it:

```bash
cd artifacts && python -m http.server 8001
# then open http://127.0.0.1:8001/distribution_linked.html
flowyaml data artifacts/distribution_linked.yaml -o artifacts/distribution_linked.data.json --revision r2
```

Regenerating the payload with a new revision updates the open page. Opening
that same HTML file straight from disk does not work, and says why: see the
next section.

## What the browser will and will not do

**A page opened from `file://` cannot fetch a sibling file.** Chrome, Edge,
Firefox and Safari all give a `file://` page an opaque origin and refuse its
requests to any other file, including one sitting in the same folder. No flag
that FlowYAML can set from inside the page changes this, and the ones that do
change it (`--allow-file-access-from-files`, disabling local file
restrictions) weaken the browser for every page the reader opens afterwards.
FlowYAML therefore does not claim, attempt or fake sibling-file reloading:

- A `data="url"` page opened from disk detects the `file:` protocol before it
  requests anything and says so on its own canvas, naming `flowyaml serve`.
- A `data="inline"` page opened from disk is a snapshot and behaves as it
  always has.

**Nothing in a browser watches a file.** The page has no way to be told that a
file on disk changed; polling a host is the only portable mechanism, which is
why the update is bounded by `poll_ms` rather than instant.

**The host is what re-reads the file**, exactly as in ERP DINFRA. FlowYAML's
host re-reads and re-validates on every data request; only the page shell,
which carries the vendored layout engine, is cached, and that cache is keyed
by the content digest of the source.

## Behaviour on an edit

- The runtime replaces its whole model table, so models may be added, renamed
  or removed by the edit.
- It stays on the model you were looking at when that model survives the
  edit; otherwise it falls back to the URL hash, then to the payload's default
  model, then to the first model.
- The breadcrumb trail is cleared, because it is a path through a model set
  that may no longer exist, and the view is refitted.
- Every cached layout is dropped: a laid-out graph belongs to the graph it was
  built from.
- In a full document the browser tab title follows the model name.
- A save that breaks the YAML is reported on the canvas, with the validation
  issues, and the previous page keeps running. Fix the file and save again;
  the next poll recovers.
- If the host goes away, the last drawing stays on screen and polling keeps
  trying quietly. A page reloaded while the host is down is a browser error
  page, not a FlowYAML one.

## Limits worth stating

- `data="url"` is a rendering mode, not an editor. The YAML is edited in your
  editor; FlowYAML draws it.
- Polling costs one small request per interval per open page. The revision
  route exists so that cost stays near zero; the data route is only re-fetched
  when the source actually changed.
- `flowyaml serve` binds the loopback interface, answers three fixed paths and
  never maps a request path onto the filesystem. It is a local authoring host,
  not a production server, and it has no authentication of any kind. Serving
  a diagram to other people is a job for your own application, using
  `flowyaml.payload`.
- Two edits saved within one poll interval collapse into one redraw; the page
  always converges on the file's current content.
- An edit that leaves the file byte-identical does not redraw, by design.
