# Releasing renpho-py

Read this checklist before creating or publishing a GitHub release.

## Naming

- Git tag: `vX.Y.Z`, for example `v1.2.1`.
- GitHub release title: `vX.Y.Z — renpho-py`, for example `v1.2.1 — renpho-py`.
- Package version: `X.Y.Z`, without the leading `v`.
- Put descriptions such as “security update” in the release notes, not the title.
- For a prerelease, use matching versions such as tag `v1.3.0rc1`, title
  `v1.3.0rc1 — renpho-py`, and package version `1.3.0rc1`; mark it as a prerelease.

Use semantic versioning: patches fix bugs, minor releases add backward-compatible
features, and major releases make breaking public API changes.

## Checklist

1. Confirm the intended PRs are merged and CI passes on the release commit.
2. Update the package version in `pyproject.toml` and `renpho/__init__.py`, update
   `uv.lock`, and add a dated changelog entry. Check that the versions agree.
3. Review the version changes in a PR and wait for CI before merging.
4. Create the tag on the validated merge commit and use the title format above.
5. Describe behavior changes, compatibility notes, validation, and contributor
   credit in the release notes. Link the relevant PRs.
6. Review carefully before publishing: publishing a GitHub release triggers
   `.github/workflows/release.yml`, which tests, builds, and publishes to PyPI.
7. Check the publishing workflow and verify the resulting package version.

An editable local dependency or a merged PR is not a published release. Consumers
may pin an exact Git commit while waiting for a versioned package release.
