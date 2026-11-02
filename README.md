# Oyster

![The Oyster card: a 3D render of an open case, the model name, and battery rings for left, right
and case](docs/screenshot.png)

An iPhone-style battery card for GNOME on Linux. Open your AirPods case near the laptop and a card
slides up from the bottom of the screen. It shows the pods, the case and three battery rings, updates
live, and slides away when you close the lid.

For AirPods Pro 2 (USB-C) the card shows a slowly turning 3D render of the open case. Other models
use flat placeholder images.

It works without connecting the AirPods. The case broadcasts its state over Bluetooth Low Energy,
and a small daemon decodes that broadcast. Design details are in `DESIGN.md`.

Supports GNOME Shell 49, 50 and 51. Tested with AirPods Pro 2 (USB-C) on openSUSE Tumbleweed with
GNOME Shell 50.5 on Wayland and BlueZ 5.87; CI runs the extension in a headless Shell of each version.
Each new GNOME Shell release is supported within four weeks of its release.

AirPods and Beats are trademarks of Apple Inc. Oyster is not affiliated with or endorsed by Apple.

## Install

Oyster has two parts: the `oysterd` daemon, which listens to Bluetooth, and the GNOME Shell
extension, which draws the card. The extension does nothing without the daemon, and
extensions.gnome.org can only ship the extension. If you installed the extension from there,
install just the daemon from a checkout of this repository: `make deps install-daemon`.

To install both:

```sh
make deps            # dbus-fast and pytest from your distribution (uses sudo)
# or, without sudo:
make deps-pip        # pip --user install of dbus-fast and pytest

make test            # unit tests
make install         # daemon + GNOME Shell extension
```

`make deps` uses zypper, dnf, apt-get or pacman, whichever you have. `make install` copies the
daemon to `~/.local/lib/oyster/` and `~/.local/bin/oysterd`, so you can delete the checkout
afterwards. The daemon is not enabled at login; the extension starts it when it needs it.

Log out and back in once after the first install. On Wayland the Shell only discovers new
extensions at login.

## Use and tune

- `make status` shows the daemon, the extension and the current decoded state.
- `make dump` prints every Apple BLE frame with its decoding. Use it to check reception.
- `make logs` follows the daemon log. `make shell-logs` follows the GNOME Shell log.

By default any AirPods or Beats model closer than about -70 dBm triggers the card. Change that in
`~/.config/oyster/config.toml`, then `systemctl --user restart oysterd`. Unknown keys and bad values
are reported in `make logs`.

```toml
rssi_threshold = -70        # dBm; raise it (e.g. -60) if other people's AirPods trigger the card
allowed_models = []         # empty = any model; e.g. [0x2420] for AirPods Pro 2 (USB-C) only
lid_close_timeout = 2.5     # seconds without broadcasts before the card hides
```

## If the card never appears

1. **Is the daemon running?** `systemctl --user status oysterd`. If the unit is not found, the
   daemon is not installed (see [Install](#install)). If it failed, `journalctl --user -u oysterd`
   says why.
2. **Is Bluetooth on?** The daemon waits for a powered adapter and says so once in its log.
3. **Does the laptop hear the case?** Run `oysterd --dump --any-model` and open the case next to
   the laptop. If frames appear but the card does not, check `allowed_models` and
   `rssi_threshold` above.
4. **Is the extension enabled?** `gnome-extensions info oyster@imperriau.github.io`. After the
   first install, log out and back in.

## Known limitations (v1)

- Someone else's AirPods close to you also trigger the card. Narrow it with `allowed_models` and a
  higher `rssi_threshold`.
- Battery levels come in 10 % steps. 1 % precision needs the direct connection planned for v2.
- The daemon keeps an active Bluetooth LE scan running. If audio stutters, see DESIGN.md §5.1.
- Only AirPods Pro 2 (USB-C) has the 3D spin. All artwork is original, not Apple's renders.

## Uninstall

```sh
make uninstall
```

## Development

- `make fake` runs a scripted fake daemon so you can work on the card without AirPods.
  Stop the real one first with `systemctl --user stop oysterd`.
- `make headless` renders the extension in an isolated headless GNOME Shell and saves screenshots.
  It needs `dbus-run-session`, which comes from `sudo zypper in dbus-1-daemon`.
- `make devkit` opens a nested Shell window. It also needs `dbus-run-session`.
- `make spin` re-renders the 3D turntable from `tools/blender/airpods_pro2_spin.py` and packs it.
  It needs Blender: `flatpak install --user flathub org.blender.Blender`.
  `make spin-preview` renders four angles to check a change quickly.

See `CONTRIBUTING.md` for how to contribute, and `docs/prior-art.md` for related projects.

## Privacy

The daemon sees the Apple proximity broadcasts of every device in range, including other people's.
It keeps only the state of the device it is tracking, in memory, publishes it on your session bus,
and never writes it to disk or sends it over the network.

## Credits

The protocol knowledge comes from the open-source projects that decoded it first:
[LibrePods](https://github.com/librepods-org/librepods),
[CAPod](https://github.com/d4rken-org/capod) and
[OpenPods](https://github.com/adolfintel/OpenPods). The decoder tests use a sample frame from CAPod's
test suite, and the fuzzy device identity follows CAPod's approach. The card follows the patterns of
GNOME Shell's `osdWindow.js` and `barLevel.js`, and the D-Bus name watching follows
[Bluetooth Battery Meter](https://github.com/maniacx/Bluetooth-Battery-Meter). These projects were
read for reference; no code was copied from them.

## Licence

Code: GPL-3.0-or-later, see `LICENSE`. Artwork in `extension/assets/`: CC-BY-SA-4.0, see
`extension/assets/LICENSE`. All artwork is original; none of it comes from Apple.
