#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Enable an extension even if the running Shell has not discovered it yet (Wayland).

Tries `gnome-extensions enable`; if the Shell does not know the uuid, appends it to the
org.gnome.shell enabled-extensions key so it loads at the next login.
"""

import ast
import subprocess
import sys

uuid = sys.argv[1]
if subprocess.run(["gnome-extensions", "enable", uuid], capture_output=True).returncode == 0:
    print(f"enabled {uuid}")
    sys.exit(0)
raw = subprocess.run(
    ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
current = ast.literal_eval(raw.replace("@as ", "")) if raw else []
if uuid not in current:
    current.append(uuid)
    subprocess.run(
        ["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(current)], check=True
    )
print(f"{uuid} added to enabled-extensions; log out and back in to load it")
