"""Plan a stable release from merged PRs; no credentials are written to disk."""

import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def api(path):
    return json.loads(run("gh", "api", path))


def next_version(current, labels):
    major, minor, patch = map(int, current.split("."))
    if "release:major" in labels:
        return f"{major + 1}.0.0"
    if "release:minor" in labels:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def release_notes(version, prs, repo, previous, head):
    lines = [f"## Changes in {version}", ""]
    for pr in sorted(prs, key=lambda p: p["number"]):
        title = " ".join(pr["title"].split())
        authors = sorted(set(pr.get("contributors", [])) | {pr["user"]["login"]})
        credit = ", ".join(f"@{author}" for author in authors)
        lines.append(f"* {title} ([#{pr['number']}]({pr['html_url']})) by {credit}")
    if not prs:
        lines.append("* Validated changes on main since the previous release")
    lines.extend(["", f"[Full comparison](https://github.com/{repo}/compare/{previous}...{head})"])
    return "\n".join(lines) + "\n"


def plan():
    repo = os.environ["GITHUB_REPOSITORY"]
    head = run("git", "rev-parse", "HEAD")
    main = run("git", "ls-remote", "origin", "refs/heads/main").split()[0]
    if head != main:
        return {"ready": "false"}  # A newer main commit must pass CI first.
    tags = [
        t
        for t in run("git", "tag", "--merged", head).splitlines()
        if re.fullmatch(r"v\d+\.\d+\.\d+", t)
    ]
    previous = max(tags, key=lambda t: tuple(map(int, t[1:].split("."))))
    if run("git", "rev-parse", f"{previous}^{{commit}}") == head:
        try:
            existing = api(f"repos/{repo}/releases/tags/{previous}")
        except subprocess.CalledProcessError:
            tags.remove(previous)
            previous = max(tags, key=lambda t: tuple(map(int, t[1:].split("."))))
        else:
            return {
                "ready": str(existing["draft"]).lower(),
                "tag": previous,
                "sha": head,
                "reuse": "true",
            }
    prs = {}
    for sha in run("git", "rev-list", "--first-parent", f"{previous}..{head}").splitlines():
        for pr in api(f"repos/{repo}/commits/{sha}/pulls?per_page=100"):
            if pr.get("merged_at") and pr["base"]["ref"] == "main":
                prs[pr["number"]] = pr
    for pr in prs.values():
        commits = api(f"repos/{repo}/pulls/{pr['number']}/commits?per_page=100")
        pr["contributors"] = [c["author"]["login"] for c in commits if c.get("author")]
    labels = {label["name"] for pr in prs.values() for label in pr["labels"]}
    project = Path("pyproject.toml")
    text = project.read_text()
    current = re.search(r'^version = "(\d+\.\d+\.\d+)"$', text, re.M).group(1)
    # A pushed version commit without its tag is an interrupted release, not a new bump.
    pending = tuple(map(int, current.split("."))) > tuple(map(int, previous[1:].split(".")))
    version = current if pending else next_version(current, labels)
    project.write_text(text.replace(f'version = "{current}"', f'version = "{version}"', 1))
    notes = release_notes(version, list(prs.values()), repo, previous, head)
    Path("release-notes.md").write_text(notes)
    changelog = Path("CHANGELOG.md")
    text = changelog.read_text()
    if f"## [{version}]" not in text:
        text = text.replace(
            "## [Unreleased]", f"## [Unreleased]\n\n## [{version}] — {date.today()}", 1
        )
        # Include attribution and PR references in the versioned changelog as well.
        position = text.find("\n## [", text.index(f"## [{version}]") + 1)
        if position < 0:
            position = len(text)
        text = text[:position] + "\n" + notes + text[position:]
        changelog.write_text(text)
    return {"ready": "true", "tag": f"v{version}", "sha": head, "reuse": "false"}


if __name__ == "__main__":
    outputs = plan()
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in outputs.items():
            output.write(f"{key}={value}\n")
