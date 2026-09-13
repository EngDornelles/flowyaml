# Releasing FlowYAML

Current release candidate: `0.1.0.0`.

Publishing is deliberately split into build and publish jobs. Only the publish
job receives GitHub's OIDC permission, and PyPI accepts it only after its exact
repository, workflow, and environment identity has been registered as a
Trusted Publisher.

## Repository-side preparation

Before publication:

1. Confirm `src/flowyaml/_version.py` contains the intended version. Both the
   package metadata and `flowyaml.__version__` read that source.
2. Run the complete suite:

   ```bash
   python -m pip install -e ".[test,browser,release]"
   playwright install chromium
   python -m pytest tests -q
   ```

3. Build and inspect both distributions:

   ```bash
   python -m build
   python -m twine check --strict dist/*
   ```

4. Install the wheel in a new virtual environment and run:

   ```bash
   python -c "import flowyaml; assert flowyaml.__version__ == '0.1.0.0'"
   flowyaml validate examples/minimal.yaml
   ```

FlowYAML itself is MIT-licensed through `LICENSE`. `NOTICE.md` and
`src/flowyaml/assets/elk.LICENSE.md` preserve the separate EPL-2.0 terms for
the unmodified bundled `elkjs` asset.

The distribution name `flowyaml` returned no project from PyPI's canonical
JSON endpoint on 2026-09-13. Availability is not a reservation; verify it again
immediately before creating the pending publisher or uploading a distribution.

## Account-side gates

Keep the GitHub repository private until Lucas explicitly chooses the public
transition. Before either publishing workflow can authenticate:

1. Protect the GitHub environments `testpypi` and `pypi`; require Lucas's
   approval for the production environment.
2. In TestPyPI, register a pending GitHub Trusted Publisher with:
   - owner: `EngDornelles`
   - repository: `flowyaml`
   - workflow: `testpypi.yml`
   - environment: `testpypi`
3. In PyPI, register the production pending publisher with:
   - owner: `EngDornelles`
   - repository: `flowyaml`
   - workflow: `release.yml`
   - environment: `pypi`

No API token belongs in GitHub secrets or this repository.

## TestPyPI gate

Run the `Publish to TestPyPI` workflow manually. After it succeeds, install from
TestPyPI while allowing dependencies to resolve from production PyPI:

```bash
python -m venv .venv-testpypi
.venv-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  flowyaml==0.1.0.0
.venv-testpypi/bin/flowyaml validate examples/minimal.yaml
```

On Windows, use `.venv-testpypi\Scripts\python.exe` and
`.venv-testpypi\Scripts\flowyaml.exe`.

## Production gate

1. Confirm the commit is clean, reviewed, and green in CI.
2. Change the changelog heading from `Unreleased` to the release date.
3. Commit that final release state.
4. Create a GitHub release whose tag is exactly `v0.1.0.0` and whose target is
   that commit.
5. Approve the protected `pypi` environment when the release workflow pauses.
6. Verify the PyPI metadata, files, hashes, provenance, and clean-environment
   installation before announcing the release.

PyPI distributions are immutable: a failed or incorrect `0.1.0.0` upload must
be corrected under a new version rather than overwritten.
