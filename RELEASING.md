# Releasing FlowYAML

Current release candidate: `0.1.2.1`.

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
   python -c "import flowyaml; assert flowyaml.__version__ == '0.1.2.1'"
   flowyaml validate examples/minimal.yaml
   ```

FlowYAML itself is MIT-licensed through `LICENSE`. `NOTICE.md` and
`src/flowyaml/assets/elk.LICENSE.md` preserve the separate EPL-2.0 terms for
the unmodified bundled `elkjs` asset.

## Account-side gates

Before the publishing workflow can authenticate, PyPI must hold the production
pending publisher:

- owner: `EngDornelles`
- repository: `flowyaml`
- workflow: `release.yml`
- environment: `pypi`

No API token belongs in GitHub secrets or this repository.

## Production gate

1. Confirm the commit is clean, reviewed, and green in CI.
2. Change the changelog heading from `Unreleased` to the release date.
3. Commit that final release state.
4. Create a GitHub release whose tag is exactly `v0.1.2.1` and whose target is
   that commit.
5. Approve the protected `pypi` environment when the release workflow pauses.
6. Verify the PyPI metadata, files, hashes, provenance, and clean-environment
   installation before announcing the release.

PyPI distributions are immutable: a failed or incorrect `0.1.2.1` upload must
be corrected under a new version rather than overwritten.
