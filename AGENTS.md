# Oyster: notes for coding agents

Oyster is an iPhone-style "case opened" battery card for AirPods on GNOME Shell. A Python daemon
(`oysterd`) decodes the AirPods BLE proximity broadcast via BlueZ and publishes it on the session
bus; a GNOME Shell extension draws the card. **`DESIGN.md` is the source of truth.** Read it before
changing behaviour. Human contributors: see `CONTRIBUTING.md`, which covers the same rules.

## Stack

- Daemon: Python ≥ 3.11 with `dbus-fast` (asyncio), nothing else at runtime. No venv for the
  installed service.
- Extension: GNOME Shell 49 to 51 ESM extension in GJS. uuid `oyster@imperriau.github.io`. No
  Gtk/Adw in `extension.js`. No settings schema yet.
- No Rust, no C, no GTK app.

## Commands

```
make deps                       # dbus-fast + pytest via zypper/dnf/apt-get/pacman (needs sudo)
make deps-pip                   # any distro, no sudo: pip --user install
make test                       # python3 -m pytest daemon/tests
make lint-deps                  # pinned ruff + mypy in .venv/, eslint in node_modules/ (no sudo)
make lint                       # ruff check + format --check, mypy --strict, eslint (GNOME config)
make format                     # apply ruff and eslint fixes
make check                      # lint + test; what CI runs (.github/workflows/ci.yml)
make pack                       # extension zip for extensions.gnome.org, in dist/
make dist                       # pack + the daemon's sdist and wheel
make release VERSION=x.y.z      # set the one version number, date CHANGELOG; tag vx.y.z to publish
make dump                       # print every Apple BLE frame with its decoding
make fake                       # scripted fake daemon (stop the real one first)
make headless                   # isolated headless Shell + fake daemon + screenshots
make spin                       # render the 3D turntable (Blender Flatpak, ~3 min) and pack it
make spin-preview               # render 4 angles only
make install-daemon             # copy to ~/.local/lib/oyster, oysterd --install-service (D-Bus activated)
make install-extension          # rsync to ~/.local/share/gnome-shell/extensions/, enable
make logs                       # journalctl --user -u oysterd -f
make shell-logs                 # journalctl -f -o cat /usr/bin/gnome-shell
make devkit                     # dbus-run-session -- gnome-shell --devkit --wayland
busctl --user monitor io.github.imperriau.Oyster
busctl --user call io.github.imperriau.Oyster /io/github/imperriau/Oyster io.github.imperriau.Oyster.Status1 GetStatus
```

## Conventions

- Packet byte indices are relative to `data[0] == 0x07` (DESIGN.md §4). Reference projects index
  differently; convert, do not copy.
- The version lives only in `daemon/oysterd/__init__.py`; change it with `make release`, never by
  hand in `metadata.json`. User-visible changes get a line under `## [Unreleased]` in CHANGELOG.md.
- `make check` passes before every commit. Lint tool versions are pinned in `requirements-dev.txt`
  and `package-lock.json`; bump them deliberately, together with the fixes they ask for.
- `decoder.py` is pure: no I/O, no asyncio, no logging. All bit logic lives there and is unit-tested
  with the sample packets in DESIGN.md §4.7.
- D-Bus names are fixed: `io.github.imperriau.Oyster`, `/io/github/imperriau/Oyster`,
  `io.github.imperriau.Oyster.Status1`. Signals carry no payload; readers fetch properties.
- Extension: everything created in `enable()` is destroyed in `disable()` (actors, signals, GLib
  sources, name watches, cancellables); null every field. No synchronous file I/O on the Shell main
  loop. Follow the GNOME extension review guidelines.
- GNOME 49 and later: no `Clutter.Container`, `Clutter.Color`, `Clutter.Image`, `Meta.Rectangle`;
  use `orientation:` not `vertical:` on `St.BoxLayout` (51 removed `vertical`).
  One code path for all supported versions; no version checks unless a real difference needs one.
- Every source file starts with `SPDX-License-Identifier: GPL-3.0-or-later` (after any shebang).
- Never add Apple artwork or downloaded models. All art is original: generated PNGs and the
  procedural Blender scene in `tools/blender/` (DESIGN.md §6.9). Rendered assets are CC-BY-SA-4.0.
- No AI co-author or attribution trailers in commit messages or PR descriptions.
- Never put hardware addresses, personal names or machine-specific paths in tracked files.

## Environment

- Wayland only: `Alt+F2 r` does not work; log out and in, or use `make devkit` / `make headless`.
- `make devkit` and `make headless` need `dbus-run-session` (on openSUSE, package `dbus-1-daemon`).
- Blender runs as a Flatpak: `flatpak run org.blender.Blender`. Pass absolute paths to it; the
  Flatpak's working directory is not the repo.
- Never `pkill` by pattern for D-Bus brokers: the user's real session bus is a
  `dbus-broker-launch --scope user` process. Kill test processes by PID or process group only.
- Machine-specific facts (adapter, paired devices, distro quirks) belong in a local, untracked
  notes file (listed in `.git/info/exclude`), not here.

## When something is unclear

DESIGN.md §8 records what is tested and verified on real hardware and what is not. Prefer the
decision recorded in DESIGN.md. If a BlueZ or GNOME behaviour contradicts the document,
verify it on the machine (`busctl`, `journalctl`, Looking Glass) and update DESIGN.md with what you
found rather than working around it silently.
