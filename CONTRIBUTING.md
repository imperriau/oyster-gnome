# Contributing to Oyster

Thanks for your interest. Oyster is maintained in spare time. Pull requests that add a model with a
frame capture, fix a bug, or improve the docs are very welcome. For larger features, please open an
issue first so we can agree on the approach.

## Layout

- `daemon/`: `oysterd`, the Python daemon. `decoder.py` turns BLE bytes into a status,
  `tracker.py` decides which device is yours and runs the lid state machine, `scanner.py` talks to
  BlueZ, `service.py` publishes on the session bus.
- `extension/`: the GNOME Shell extension that draws the card.
- `tools/`: the headless Shell test, artwork generators and the Blender turntable.
- `DESIGN.md`: the architecture and protocol reference. Read §4 (the packet) and §5 (the daemon)
  before changing either.

## Getting set up

You need GNOME Shell 49, 50 or 51, BlueZ, Python ≥ 3.11 and `dbus-fast`.

```sh
make deps-pip        # dbus-fast and pytest for your user (or install your distro's packages)
make test            # unit tests, no hardware needed
make lint-deps       # ruff and mypy in .venv/, eslint in node_modules/ (needs npm, no sudo)
make check           # lint + tests, the same as CI; run it before opening a pull request
```

`make format` applies ruff's and ESLint's fixes. The Python code is formatted by `ruff format`
and type-checked with `mypy --strict`; the extension follows GNOME's ESLint config
(`eslint-config-gnome`, as used by gnome-shell-extensions).

Working on the card without AirPods:

```sh
systemctl --user stop oysterd    # if you installed it (the extension may restart it on login)
make fake                        # scripted fake daemon on the session bus
make headless                    # headless Shell + fake daemon, saves screenshots
make devkit                      # nested Shell window for interactive work
```

`make headless` and `make devkit` need `dbus-run-session` (package `dbus-1-daemon` on openSUSE,
`dbus-daemon` or `dbus` elsewhere).

Checking reception from real hardware:

```sh
make dump            # prints every Apple BLE frame and how it decodes
```

## Rules

- **Byte indices** in the decoder are relative to `data[0] == 0x07` (DESIGN.md §4). Other projects
  index differently; convert, do not copy.
- **`decoder.py` stays pure**: no I/O, no logging, no asyncio. Every bit of protocol logic lives
  there and has a unit test.
- **The D-Bus interface is a public API.** The names in DESIGN.md §5.4 do not change; additions go
  into a new versioned interface.
- **Extension lifecycle**: everything created in `enable()` is destroyed in `disable()`, and no
  synchronous file I/O runs on the Shell main loop. Follow the
  [GNOME extension review guidelines](https://gjs.guide/extensions/review-guidelines/review-guidelines.html).
- **Licence headers**: every source file starts with `SPDX-License-Identifier: GPL-3.0-or-later`.
- **No AI attribution trailers** in commit messages or PR descriptions.

## Artwork

All artwork must be original. Do not submit Apple's renders, product photos, or models downloaded
from Sketchfab or similar sites, even ones labelled free. The 3D turntable is built from primitives
by `tools/blender/airpods_pro2_spin.py`; new models should follow the same approach. Contributed
artwork is licensed CC-BY-SA-4.0 (see `extension/assets/LICENSE`).

## Adding a model

1. Capture frames with `make dump` while opening and closing the case, with pods in and out.
2. Add the model id to `daemon/oysterd/models.py`, tagged with its sources the way the other rows
   are (the key is above the table). Your capture counts as a source.
3. Add a decoder test using one of your captured frames. Only the payload bytes go in the test;
   leave out the Bluetooth address printed next to them.
4. Optionally add `extension/assets/<id>/` artwork.

## Reporting a bug

Use the issue template. The most useful attachments are your GNOME Shell and BlueZ versions, your
Bluetooth adapter, and a few lines of `make dump` output taken while opening the case.

## Licence

By contributing you agree that your code is licensed under GPL-3.0-or-later and your artwork under
CC-BY-SA-4.0.
