#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the one Oyster version number consistent (DESIGN.md §7).

The version lives in daemon/oysterd/__init__.py; pyproject.toml reads it from there. The
extension's metadata.json "version-name" and the CHANGELOG.md headings must agree with it.

  tools/version.py check              files agree (make lint)
  tools/version.py check --tag v1.2.3 also: the tag matches and its changelog section is dated
  tools/version.py set 1.2.3          write the version, date the [Unreleased] changelog section
  tools/version.py notes              print the current version's changelog section
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INIT = REPO / "daemon/oysterd/__init__.py"
METADATA = REPO / "extension/metadata.json"
CHANGELOG = REPO / "CHANGELOG.md"

INIT_RE = re.compile(r'^__version__ = "([^"]*)"$', re.M)
NAME_RE = re.compile(r'^(\s*"version-name":\s*)"([^"]*)"', re.M)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def current() -> str:
    m = INIT_RE.search(INIT.read_text())
    if not m:
        sys.exit(f"{INIT}: no __version__ line")
    return m.group(1)


def section(version: str) -> tuple[str, str] | None:
    """Return (heading, body) of the changelog section for version, or None."""
    text = CHANGELOG.read_text()
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*$", text, re.M)
    if not m:
        return None
    end = re.search(r"^## ", text[m.end() :], re.M)
    body = text[m.end() : m.end() + end.start()] if end else text[m.end() :]
    return m.group(0), body.strip()


def check(tag: str | None) -> list[str]:
    version = current()
    problems = []
    if not SEMVER_RE.match(version):
        problems.append(f"{INIT}: version {version!r} is not X.Y.Z")
    name = json.loads(METADATA.read_text()).get("version-name")
    if name != version:
        problems.append(f"{METADATA}: version-name is {name!r}, {INIT.name} says {version!r}")
    if tag is not None:
        if tag != f"v{version}":
            problems.append(f"tag {tag} does not match version {version}")
        found = section(version)
        if found is None:
            problems.append(f"{CHANGELOG.name}: no section ## [{version}]")
        elif not re.search(r" - \d{4}-\d{2}-\d{2}$", found[0]):
            problems.append(f"{CHANGELOG.name}: {found[0]!r} has no release date")
    return problems


def set_version(version: str) -> None:
    if not SEMVER_RE.match(version):
        sys.exit(f"version must be X.Y.Z, got {version!r}")
    INIT.write_text(INIT_RE.sub(f'__version__ = "{version}"', INIT.read_text(), count=1))
    METADATA.write_text(NAME_RE.sub(rf'\g<1>"{version}"', METADATA.read_text(), count=1))
    text = CHANGELOG.read_text()
    if section(version) is None:
        today = datetime.date.today().isoformat()
        if "## [Unreleased]" not in text:
            sys.exit(f"{CHANGELOG.name}: no ## [Unreleased] section to release")
        text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{version}] - {today}", 1)
        CHANGELOG.write_text(text)
    print(
        f"version {version}: {INIT.relative_to(REPO)}, {METADATA.relative_to(REPO)}, "
        f"{CHANGELOG.name}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--tag")
    s = sub.add_parser("set")
    s.add_argument("version")
    sub.add_parser("notes")
    a = p.parse_args()

    if a.cmd == "check":
        problems = check(a.tag)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    if a.cmd == "set":
        set_version(a.version)
        return 0
    found = section(current())
    if found is None:
        sys.exit(f"{CHANGELOG.name}: no section for {current()}")
    print(found[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
