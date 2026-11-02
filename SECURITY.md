# Security policy

## What Oyster does

`oysterd` runs as your user, not as root. It asks BlueZ over the system bus to run a Bluetooth LE
scan, decodes Apple proximity broadcasts from any nearby device, and publishes the status of one
device on your session bus. It stores nothing, opens no network sockets, and writes no files. The
GNOME Shell extension only reads the session bus.

## Reporting a vulnerability

Please report security problems privately through GitHub's
[private vulnerability reporting](https://github.com/imperriau/oyster-gnome/security/advisories/new)
rather than in a public issue. Include the version, what you found, and how to reproduce it.

You should get a reply within a week. Fixes are released as soon as they are ready, and the
advisory is published once a fixed version is available.

## Supported versions

Only the latest release receives fixes.
