"""Offline regression coverage for version planning and release recovery."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "prepare_release", Path(__file__).parents[1] / "scripts" / "prepare_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (set(), "1.2.2"),
        ({"release:minor"}, "1.3.0"),
        ({"release:major", "release:minor"}, "2.0.0"),
    ],
)
def test_version_precedence(labels, expected):
    assert release.next_version("1.2.1", labels) == expected


@pytest.fixture
def planner(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    Path("pyproject.toml").write_text('version = "1.2.1"\n')
    Path("CHANGELOG.md").write_text("## [Unreleased]\n\n- Feature\n\n## [1.2.1]\n")
    state = {"main": "head", "tag_sha": "old", "draft": True, "missing_release": False}

    def run(*args):
        key = args[1:]
        if key == ("rev-parse", "HEAD"):
            return "head"
        if key[0] == "ls-remote":
            return f"{state['main']} refs/heads/main"
        if key[0] == "tag":
            return "v1.2.1"
        if key[0] == "rev-parse":
            return state["tag_sha"]
        if key[0] == "rev-list":
            return "merge1\nmerge2"
        raise AssertionError(args)

    def api(path):
        if "/commits?" in path:
            return [{"author": {"login": "original-author"}}]
        if "/releases/" in path:
            if state["missing_release"]:
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            return {"draft": state["draft"]}
        return [
            {
                "number": 8,
                "title": "Add profiles",
                "merged_at": "date",
                "base": {"ref": "main"},
                "html_url": "https://example.invalid/pr/8",
                "labels": [{"name": "release:minor"}],
                "user": {"login": "contributor"},
            }
        ]

    monkeypatch.setattr(release, "run", run)
    monkeypatch.setattr(release, "api", api)
    return state


def test_stale_ci_does_not_release(planner):
    planner["main"] = "newer"
    assert release.plan() == {"ready": "false"}
    assert Path("pyproject.toml").read_text() == 'version = "1.2.1"\n'


def test_plan_bumps_minor_and_credits_each_pr_once(planner):
    result = release.plan()
    assert result["tag"] == "v1.3.0"
    assert 'version = "1.3.0"' in Path("pyproject.toml").read_text()
    notes = Path("release-notes.md").read_text()
    assert notes.count("[#8]") == 1
    assert "@contributor" in notes
    assert "@original-author" in notes
    assert "## [Unreleased]\n\n## [1.3.0]" in Path("CHANGELOG.md").read_text()


def test_retry_pushed_version_does_not_bump_again(planner):
    release.plan()
    assert release.plan()["tag"] == "v1.3.0"
    assert Path("CHANGELOG.md").read_text().count("## [1.3.0]") == 1


@pytest.mark.parametrize("draft", [False, True])
def test_tagged_release_resume_or_noop(planner, draft):
    planner.update(tag_sha="head", draft=draft)
    result = release.plan()
    assert result["ready"] == str(draft).lower()
    assert result["reuse"] == "true"


def test_release_notes_keep_title_as_data():
    notes = release.release_notes(
        "1.3.0",
        [
            {
                "number": 1,
                "title": "fix `$(echo title)`\ntext",
                "html_url": "https://example.invalid/1",
                "user": {"login": "author"},
            }
        ],
        "owner/repo",
        "v1.2.1",
        "abc",
    )
    assert "by @author" in notes
    assert "$(echo title)" in notes
