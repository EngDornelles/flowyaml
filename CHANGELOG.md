# Changelog

All notable FlowYAML changes are recorded here.

## 0.1.2.1 - 2026-09-13

Beta, and the parity that was missing from 0.1.2.0.

- **`serve` now takes the same presentation options as `render`**: `scheme`,
  `levels`, `strings` and `lang` reach `flowyaml.serve`, `create_server`,
  `LinkedSource` and the `serve` subcommand. The live host is the editing
  path - it is where those options get chosen - so it was the one place they
  could not be missing. A bad option is refused when it is given rather than
  on the first request, because a server that starts and then serves an error
  page is a worse answer than one that refuses to start.
- **Development status is now Beta.** The renderer does what it claims, on
  four Python versions, with the offline guarantee under test. From here a
  change to the public surface is an event rather than a routine.
- Documentation garbage collection: the superseded implementation brief is no
  longer tracked, the release checklist lost three paragraphs describing gates
  that do not exist, the README installs from PyPI, and the theme section
  describes themes rather than reciting hex values.

## 0.1.2.0 - 2026-09-13

Presentation release. The graph is unchanged; what surrounds it is not.

- **Light and dark.** Every theme now carries a dark token table beside its
  light one, and both ship in every artifact. `scheme="auto"` is the default
  and follows the reader's system setting, because a file that outlives the
  moment it was written cannot know which machine will open it. `scheme="light"`
  and `scheme="dark"` pin it, and `data-fy-scheme` on the mount lets a host
  override either. Paper is one palette in both schemes.
- **Breadcrumb or snapshot.** `levels="breadcrumb"` keeps the horizontal trail
  in the toolbar and stays the default. `levels="snapshot"` replaces it with a
  stripe of the levels above, the nearest carrying a picture of the diagram the
  reader came from, plus a level counter. The stripe spends vertical room to buy
  recall, so the flows that want it are the wide ones.
- **A drawer of next levels.** Every subprocess of the current level, listed
  under the canvas and closed until asked for. The canvas already offered them,
  but only to a reader who could find them on it; this is the same navigation
  for a keyboard, a screen reader and a narrow screen.
- **Idiom.** `strings=` overrides the text the runtime writes for itself -
  buttons, the canvas hint, screen-reader labels and failure messages - merged
  over the defaults, with an unknown key refused rather than ignored. `lang=`
  and `meta.lang` set the document language. Until now a Portuguese diagram
  rendered inside English furniture and announced itself as an English page,
  and because `open` and `destination` are spoken joined to the author's own
  label, a screen reader read one sentence in two languages. That table is also
  BPMN's vocabulary, which every author inherited whether or not they were
  modelling a business process.
- Responsive rules for narrow and short viewports.
- A second worked example, `examples/notebooks/cozinha`: a six-level flow
  for choosing dinner from what the kitchen already holds, written in
  Portuguese so the idiom options are shown doing their job rather than
  described. It ships as a notebook, as `cozinha_flowyaml.py` for anyone
  without a Jupyter to run it in, and as the rendered HTML beside its YAML.

## 0.1.1.0 - 2026-09-13

Including notebook examples for functionalities usage.

## 0.1.0.0 - 2026-09-13

First public-package candidate and second implementation build.

- Render YAML-defined process flows as standalone, self-sufficient HTML.
- Render instance-scoped fragments for host applications.
- Keep an HTTP-served page linked to an actively edited YAML source.
- Import supported Mermaid flowcharts and BPMN 2.0 XML into the FlowYAML model.
- Navigate embedded subprocess levels without network access.
- Provide a Python API and `flowyaml` command-line interface.
- Bundle `elkjs` 0.9.3 with its EPL-2.0 notice for offline layout.
- Cover rendering, validation, serialization, imports, live updates, browser
  behavior, accessibility, and offline operation with automated tests.

The internal `0.0.0.0` build used YAML-linked delivery by default and did not
yet include standalone HTML output.
