# Third-party notices

FlowYAML redistributes the following component as package data.

## elkjs 0.9.3

- File: `src/flowyaml/assets/elk.bundled.js` (UMD browser bundle)
- Project: https://github.com/kieler/elkjs
- Licence: Eclipse Public License 2.0
- Full licence text: `src/flowyaml/assets/elk.LICENSE.md`
- Version record: `src/flowyaml/assets/elk.VERSION.txt`

The bundle is embedded verbatim and unmodified. FlowYAML wraps it in an
`if (typeof window.ELK === "undefined") { ... }` guard at render time so that
mounting several fragments on one page evaluates it once. The wrapper adds no
code to the bundle itself.

The bundle runs its layout in process. FlowYAML never passes `workerUrl`, so no
web worker is constructed and no script is fetched.
