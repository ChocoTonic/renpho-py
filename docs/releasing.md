# Releasing renpho-py

## Automatic releases

After a push to `main` passes the complete CI workflow, `release.yml` automatically:

1. Finds changes since the latest stable tag and collects merged PR links and
   contributor credit, including the authors of commits within each PR.
2. Selects the next version, updates `pyproject.toml`, `uv.lock`, and the dated
   changelog, and validates the versioned source with tests, Ruff, and mypy.
3. Commits the version changes, creates the tag, and prepares a draft release.
4. Builds that exact commit, checks the packages, and publishes them to PyPI
   using the existing `release.yml` trusted publisher and `pypi` environment.
5. Attaches the packages and publishes the GitHub release only after PyPI succeeds.

No manual release PR or publishing click is needed. Rapid merges can ship together
in one release; their PRs are all linked. A stale CI run does not release a newer,
untested main commit. Runs are serialized, and version pushes use normal
fast-forward checks, so concurrent changes cannot be overwritten. Release commits
use `GITHUB_TOKEN`, which does not recursively trigger push/release workflows.

## Version selection

Every eligible main change defaults to a patch release. Before merging, label PRs:

- `release:minor` for backward-compatible public API additions.
- `release:major` for breaking public API changes.
- `release:patch` is optional and equivalent to the default.

The highest label among all unreleased merged PRs wins. Documentation and workflow
changes also default to patch, so every merged PR can be traced to a release.
Package versions are read from `pyproject.toml`; `renpho.__version__` reads the
installed package metadata and does not need a separate source version change.

## Naming

- Git tag: `vX.Y.Z`, for example `v1.3.0`.
- GitHub release title: `vX.Y.Z — renpho-py`, for example `v1.3.0 — renpho-py`.
- Package version: `X.Y.Z`, without the leading `v`.
- Descriptions such as “security update” belong in the notes, not the title.

Automation creates stable releases only. Prereleases require a separate deliberate
release process with matching tag and package versions and a prerelease marker.

## Recovery

Inspect the failed `Release to PyPI` run and fix the underlying failure. Rerun that
workflow or dispatch `release.yml` on `main`. Manual recovery verifies successful
push CI for the source commit, including the parent of an interrupted version-only
release commit. An existing draft or a version commit awaiting its tag resumes the
same version; already published GitHub releases are no-ops. PyPI retries skip
existing package files, and GitHub attachments can be replaced on retry.

Do not delete or move published tags or attempt to overwrite a PyPI version.
The automated workflow replaces the former manual GitHub-release trigger, avoiding
a second publisher for the same version. A Git commit pin remains useful while a
release is pending; update both a consumer's source pin and lockfile together.
