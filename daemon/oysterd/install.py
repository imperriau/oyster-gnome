# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the per-user systemd unit and D-Bus activation file (DESIGN.md §5.6).

`oysterd --install-service` writes both files, pointing at the oysterd command that ran it, so the
same step works for `make install-daemon`, `pipx install` and a plain `pip install --user`. Distro
packages ship their own copies of the templates in data/ and do not use this.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from importlib import resources
from pathlib import Path

UNIT = "oysterd.service"
DBUS_SERVICE = "io.github.imperriau.Oyster.service"

Run = Callable[[list[str]], int]


class InstallError(Exception):
    pass


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def unit_path() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "systemd" / "user" / UNIT


def dbus_service_path() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "dbus-1" / "services" / DBUS_SERVICE


def admin_unit_path() -> Path:
    """Where `systemctl --user edit --full` and the pre-0.2 Makefile put the unit.

    A unit here takes precedence over ours, so it has to be dealt with.
    """
    return _xdg("XDG_CONFIG_HOME", ".config") / "systemd" / "user" / UNIT


def exec_path(argv0: str) -> str:
    """The absolute path of the running oysterd command.

    Not resolved through symlinks: pipx's ~/.local/bin/oysterd link survives upgrades, its target
    does not.
    """
    p = Path(argv0)
    if p.name != "oysterd":
        raise InstallError("run the installed `oysterd` command, not `python3 -m oysterd`")
    path = os.path.abspath(p)
    if any(c.isspace() for c in path):
        raise InstallError(f"the oysterd path contains whitespace: {path!r}")
    return path


def render(name: str, exe: str) -> str:
    template = resources.files("oysterd").joinpath("data", name).read_text(encoding="utf-8")
    return template.replace("@EXEC@", exe)


def _run(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd, check=False).returncode
    except FileNotFoundError:
        return 127


def _reload(run: Run) -> None:
    if run(["systemctl", "--user", "daemon-reload"]) != 0:
        print(
            "warning: `systemctl --user daemon-reload` failed; is a systemd user session running?"
        )
    # dbus-broker and dbus-daemon only rescan service files on ReloadConfig.
    if (
        run(
            [
                "busctl",
                "--user",
                "call",
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ReloadConfig",
            ]
        )
        != 0
    ):
        print(
            "warning: could not ask the session bus to reload; log out and in to activate oysterd"
        )


def install_service(argv0: str, run: Run = _run) -> None:
    exe = exec_path(argv0)

    admin = admin_unit_path()
    if admin.exists():
        if "PYTHONPATH=" in admin.read_text(encoding="utf-8", errors="replace"):
            # Left by the old Makefile, which ran the daemon from the git checkout.
            run(["systemctl", "--user", "disable", "--now", UNIT])
            admin.unlink()
            print(f"removed old unit {admin}")
        else:
            print(f"warning: {admin} overrides the unit installed here; remove it to use this one")

    for path, name in ((unit_path(), UNIT), (dbus_service_path(), DBUS_SERVICE)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(name, exe), encoding="utf-8")
        print(f"wrote {path}")

    _reload(run)
    # Start (or restart onto the new code) now; later the extension starts it through D-Bus.
    if run(["systemctl", "--user", "restart", UNIT]) == 0:
        print("oysterd is running; the GNOME Shell extension starts it on demand from now on")
    else:
        print(f"warning: could not start {UNIT}; see `journalctl --user -u oysterd`")


def uninstall_service(run: Run = _run) -> None:
    if unit_path().exists():
        run(["systemctl", "--user", "disable", "--now", UNIT])
    for path in (unit_path(), dbus_service_path()):
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    _reload(run)
