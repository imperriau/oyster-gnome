# oysterd

The daemon half of [Oyster](https://github.com/imperriau/oyster-gnome), an iPhone-style battery
card for AirPods on GNOME. Open your AirPods case near the laptop and a card slides up showing the
pods, the case and their battery levels.

`oysterd` listens to the Bluetooth Low Energy proximity broadcast that AirPods and Beats send when
the case opens, decodes it through BlueZ, and publishes the battery, charging, lid and in-ear state
on the session bus as `io.github.imperriau.Oyster.Status1`. It needs no pairing or connection.

The card itself is drawn by the Oyster GNOME Shell extension (GNOME Shell 49, 50 and 51). This
package does nothing visible on its own.

## Install

```sh
pipx install oysterd
oysterd --install-service
```

`--install-service` writes a systemd user unit and a D-Bus activation file that point at this
`oysterd`. The daemon is not enabled at login; the extension starts it when it needs it. Then
install the Oyster extension and log out and back in once.

Requirements: Linux with a systemd user session, BlueZ, a Bluetooth LE adapter, and Python 3.11 or
later.

## Check and tune

- `oysterd --dump --any-model` prints every Apple BLE frame with its decoding. Open the case next
  to the laptop to check reception.
- `journalctl --user -u oysterd` shows the daemon log.
- `~/.config/oyster/config.toml` sets the signal-strength threshold, the allowed models and the
  timeouts. See the [project README](https://github.com/imperriau/oyster-gnome#use-and-tune).

## Privacy

The daemon sees the Apple proximity broadcasts of every device in range, including other people's.
It keeps only the state of the device it is tracking, in memory, publishes it on your session bus,
and never writes it to disk or sends it over the network.

## Licence

GPL-3.0-or-later. AirPods and Beats are trademarks of Apple Inc. Oyster is not affiliated with or
endorsed by Apple.
