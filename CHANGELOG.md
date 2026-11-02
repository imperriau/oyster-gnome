# Changelog

All notable changes to Oyster. The daemon (`oysterd`) and the GNOME Shell extension share one
version number. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/). The D-Bus interface
`io.github.imperriau.Oyster.Status1` is the public API that semantic versioning refers to.

## [Unreleased]

## [0.1.0] - 2026-11-02

First public release.

### Added

- `oysterd`, a daemon that decodes the AirPods and Beats Bluetooth LE proximity broadcast through
  BlueZ and publishes the battery, charging, lid and in-ear state on the session bus as
  `io.github.imperriau.Oyster.Status1`. It needs no pairing or connection.
- 30 AirPods and Beats models, each with its sources recorded in `models.py`.
- `oysterd --install-service`, which installs a sandboxed systemd user unit and a D-Bus activation
  file. The daemon starts only when the extension asks for it.
- A GNOME Shell 49, 50 and 51 extension that shows a battery card when the case opens, with a 3D turntable
  for AirPods Pro 2 (USB-C) and flat artwork for other models.
- A one-time notification from the extension when `oysterd` is missing or does not start.
- `~/.config/oyster/config.toml` for the signal-strength threshold, the allowed models and the
  timeouts, with unknown keys and bad values reported in the log.
