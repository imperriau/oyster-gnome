# Oyster: lid-open AirPods battery card for GNOME on Linux

The architecture and protocol reference for Oyster. Facts were researched against the BlueZ 5.87
source and docs, GNOME Shell 49 to 51, and the LibrePods, CAPod and OpenPods decoders. Where a fact
is unverified it is marked **(unverified)**; §8 lists what has and has not been tested on real
hardware.

---

## 1. Goal and non-goals

**Goal.** When the user opens their AirPods case near their Linux laptop, a card slides up from the
bottom centre of the screen, like the iPhone sheet: a picture of the pods and case, the model name,
and three battery rings (left, right, case) with charging indicators. The card updates live while the
lid is open and slides away when the lid closes. Nothing has to be connected; the data comes from the
Bluetooth Low Energy advertisement the case broadcasts.

**Non-goals for 0.1** (see §11):
- No direct AAP (Apple Accessory Protocol) connection, so no 1 % battery, noise-control modes or
  conversational awareness.
- No cryptographic ownership check (IRK / encryption key). Ownership is model id + signal strength.
- No panel indicator, no lock-screen display, no preferences window.
- No Apple artwork. All art is original (§6.9).
- No AdvertisementMonitor route (it needs `Experimental = true` in main.conf). Filtered discovery only.

---

## 2. Architecture

Two cooperating processes:

```
   AirPods case (lid open)
        │  BLE advertisement, manufacturer data 0x004C, type 0x07
        ▼
   bluetoothd (BlueZ 5.87)  ── org.bluez.Device1.ManufacturerData / RSSI on the SYSTEM bus
        │
        ▼
   oysterd (Python 3.13, dbus-fast, asyncio)         [systemd --user service]
     scanner → decoder → tracker → service
        │  io.github.imperriau.Oyster.Status1 on the SESSION bus: properties + LidOpened/LidClosed signals
        ▼
   GNOME Shell extension oyster@imperriau.github.io (GJS, ESM)
     dbusClient → card (Clutter/St overlay, bottom centre, slide in/out) → batteryRing, artwork
```

**Why two processes.** On Wayland an ordinary GTK window cannot position itself at the bottom
centre over everything; only GNOME Shell can draw there. Putting BlueZ handling in a separate daemon
keeps the extension tiny (less to break on GNOME upgrades), lets the daemon be tested with `busctl`
without a Shell, and survives Shell restarts and extension toggles. The daemon publishes decoded state
only; all presentation policy lives in the extension.

**Bus usage.** The daemon talks to BlueZ on the **system** bus and exports its own interface on the
**session** bus. The extension only touches the session bus. The default BlueZ D-Bus policy
(`/usr/share/dbus-1/system.d/bluetooth.conf`) allows any local user to call `org.bluez`, so no polkit
or group changes are needed.

---

## 3. Repository layout

```
oyster-gnome/
├── DESIGN.md                  this file
├── AGENTS.md                  conventions and commands for coding agents
├── CONTRIBUTING.md            the same rules for human contributors
├── README.md                  user-facing install, tuning and troubleshooting
├── CHANGELOG.md               one version for daemon and extension; release notes come from here
├── Makefile                   install, test, lint, pack, release, development helpers (§7)
├── ruff.toml                  ruff lint and format settings for daemon/ and tools/
├── requirements-dev.txt       pinned ruff, mypy and build, for make lint-deps
├── package.json               eslint + eslint-config-gnome (dev only; never installed with the extension)
├── eslint.config.js           GNOME's shared ESLint config plus GJS globals
├── .github/workflows/         ci.yml (lint, tests, headless Shell per version), release.yml
├── daemon/
│   ├── pyproject.toml         package oysterd, entry point oysterd, deps: dbus-fast
│   ├── README.md              the PyPI description
│   ├── LICENSE                symlink to ../LICENSE, so the sdist and wheel carry it
│   ├── oysterd/
│   │   ├── __init__.py        the one version number
│   │   ├── __main__.py        CLI (§5.5)
│   │   ├── models.py          model, colour and connection-state tables, with sources per row
│   │   ├── decoder.py         pure: bytes -> PodsStatus (no I/O, no asyncio)
│   │   ├── scanner.py         BlueZ discovery session on the system bus, yields RawFrame
│   │   ├── tracker.py         ownership filter, fuzzy identity, lid state machine, timeouts
│   │   ├── service.py         io.github.imperriau.Oyster.Status1 export on the session bus
│   │   ├── config.py          TOML config loading and validation
│   │   ├── install.py         --install-service / --uninstall-service (§5.6)
│   │   └── data/              oysterd.service and io.github.imperriau.Oyster.service templates
│   └── tests/                 pytest suites, plus fake_daemon.py for make fake and make headless
├── extension/
│   ├── metadata.json
│   ├── extension.js           enable()/disable() only; wires client, notice and card
│   ├── stylesheet.css
│   ├── lib/
│   │   ├── dbusClient.js      proxy + name watch for io.github.imperriau.Oyster
│   │   ├── daemonNotice.js    one-time notification when oysterd is missing or not starting
│   │   ├── card.js            the overlay actor (slide in/out, layout)
│   │   ├── batteryRing.js     St.DrawingArea ring with cairo
│   │   ├── artwork.js         model id -> static parts and optional spin
│   │   └── spinView.js        sprite-sheet turntable (§6.9)
│   └── assets/                generic/ and 2420/ art, LICENSE (CC-BY-SA-4.0)
├── docs/                      screenshot, prior-art comparison
└── tools/                     headless test, enable fallback, artwork generators, Blender scene, version.py
```

The extension directory is installed verbatim to
`~/.local/share/gnome-shell/extensions/oyster@imperriau.github.io/`. The directory name must equal
the uuid.

---

## 4. Apple proximity-pairing advertisement

### 4.1 Where it appears

BlueZ exposes each received advertisement as properties on an `org.bluez.Device1` object:
`ManufacturerData` is `a{qv}` keyed by company id; key `0x004C` (Apple) maps to a byte array `ay`.
The AirPods case sends a Continuity message of type `0x07` ("proximity pairing"). All byte indices
below are relative to the start of that byte array, so `data[0] == 0x07`.

Caution when reading reference code: CAPod strips the type and length first, so CAPod `data[i]`
equals `data[i+2]` here. OpenPods indexes hex-string characters. LibrePods' Linux code uses the same
indexing as this document.

### 4.2 Byte layout (27 bytes for genuine Apple devices)

Sample from CAPod's `AirPodsPro2Test.kt`:

```
07 19 01 14 20 55 88 F9 51 00 04 | 20 50 03 CA D5 C9 AC 0F FA 84 78 94 5A 4D DF F5
```

| Index | Field | Rule |
|---|---|---|
| 0 | Message type | must be `0x07` |
| 1 | Payload length | must be `0x19` (25). Clones send 19; reject. |
| 2 | Prefix | must be `0x01` (paired/normal). `0x00` = pairing mode, different layout, reject. |
| 3..4 | Model id | **big-endian**: `model = (data[3] << 8) \| data[4]`. Sample: `0x1420`. |
| 5 | Status flags | see 4.3 |
| 6 | Pod battery nibbles | see 4.4 |
| 7 | Charging flags (high nibble) and case battery (low nibble) | see 4.4 |
| 8 | Lid byte | see 4.5 |
| 9 | Colour | `0x00` White, `0x01` Black, `0x02` Red, `0x03` Blue, `0x04` Pink, `0x05` Gray, `0x06` Silver, `0x07` Gold, `0x08` Rose Gold, `0x09` Space Gray, `0x0A` Dark Blue, `0x0B` Light Blue, `0x0C` Yellow |
| 10 | Connection state | `0x00` Disconnected, `0x04` Idle, `0x05` Music, `0x06` Call, `0x07` Ringing, `0x09` Hanging up |
| 11..26 | Encrypted payload | AES-128-ECB, needs the ENC_KEY obtained over AAP. **Ignored in 0.1.** |

### 4.3 Status byte `data[5]`

| Mask | Meaning |
|---|---|
| `0x20` | Primary pod is **left**. Define `flipped = (data[5] & 0x20) == 0`. |
| `0x40` | The pod that sent this frame is in the case ("this pod in case"). |
| `0x10` | One pod is in the case. |
| `0x04` | Both pods are in the case. |
| `0x08`, `0x02` | In-ear bits. Which is left depends on `xor = flipped ^ thisPodInCase`: `leftInEar = xor ? (s & 0x08) : (s & 0x02)`, `rightInEar = xor ? (s & 0x02) : (s & 0x08)`. |

### 4.4 Battery and charging

```
b6 = data[6]
leftNibble  = flipped ? (b6 >> 4) & 0xF : b6 & 0xF
rightNibble = flipped ? b6 & 0xF        : (b6 >> 4) & 0xF
level(n)    = n == 0xF ? -1 (unknown) : min(n, 10) * 10        # 0..100 in 10 % steps

flags = (data[7] >> 4) & 0xF
rightCharging = flipped ? flags & 0x01 : flags & 0x02
leftCharging  = flipped ? flags & 0x02 : flags & 0x01
caseCharging  = flags & 0x04
caseNibble    = data[7] & 0xF            # same level() mapping, 0xF unknown
```

Nibble values 0xB..0xE have been observed; LibrePods Android and CAPod clamp them to 100 %, so clamp.
Single-battery products (AirPods Max, most Beats) carry one level in the **low** nibble of `data[6]`;
report it as `left`, leave `right = -1`, and mark the model kind as `single` in the model table.

### 4.5 Lid byte `data[8]`

- `lidCounter = data[8] & 0x07`, increments on rapid open/close; not used for logic.
- `lidBit = (data[8] >> 3) & 0x01`, **0 = OPEN, 1 = CLOSED**.
- The bit is only meaningful when the frame came from a pod inside the case: trust it only if
  `(data[5] & 0x40) || (data[5] & 0x04)`. A frame from the out-of-case primary pod carries a stale
  lid byte (CAPod verified phantom OPEN on Pro 1 and Pro 3). Otherwise report `Unknown`.
- When no case bits are set at all (`0x40`, `0x10`, `0x04` all clear) the pods are out of the case;
  report `NotInCase`.
- Lid close is detected by the bit flipping to 1 **or** by silence: the case stops broadcasting shortly
  after closing. LibrePods uses 2.5 s of silence as "closed". Use the same default.

### 4.6 Model id table

Low byte is always `0x20` for genuine devices. `kind` is `dual` (two pods + case) or `single`.

| Id | Product | kind |
|---|---|---|
| 0x0220 | AirPods (1st gen) | dual |
| 0x0F20 | AirPods (2nd gen) | dual |
| 0x1320 | AirPods (3rd gen) | dual |
| 0x1920 | AirPods 4 | dual |
| 0x1B20 | AirPods 4 (ANC) | dual |
| 0x3620 | AirPods (5th gen) | dual |
| 0x3020 | AirPods (5th gen, wireless case) | dual |
| 0x0E20 | AirPods Pro | dual |
| 0x1420 | AirPods Pro 2 (Lightning) | dual |
| 0x2420 | AirPods Pro 2 (USB-C) | dual |
| 0x2720 | AirPods Pro 3 | dual |
| 0x0A20 | AirPods Max (Lightning) | single |
| 0x1F20 | AirPods Max (USB-C) | single |
| 0x2D20 | AirPods Max 2 | single |
| 0x0320 | Powerbeats 3 | single |
| 0x0520 | BeatsX | single |
| 0x0620 | Beats Solo 3 | single |
| 0x0920 | Beats Studio 3 | single |
| 0x0B20 | Powerbeats Pro | dual |
| 0x0C20 | Beats Solo Pro | single |
| 0x0D20 | Powerbeats 4 | single |
| 0x1020 | Beats Flex | single |
| 0x1120 | Beats Studio Buds | dual |
| 0x1220 | Beats Fit Pro | dual |
| 0x1620 | Beats Studio Buds+ | dual |
| 0x1720 | Beats Studio Pro | single |
| 0x1D20 | Powerbeats Pro 2 | dual |
| 0x2520 | Beats Solo 4 | single |
| 0x2620 | Beats Solo Buds | dual |
| 0x3820 | Beats 360 | single |

Each row's sources (CAPod, LibrePods, OpenPods, continuity, AirPodsDesktop, MagicPodsCore, with
the commit read) are recorded next to it in `models.py`. CAPod lists all 30 ids and is the
authority for `kind`. Beats 360 (`0x3820`) is `single`: CAPod decodes it as a headset and its
captured frame carries one battery level. Only `0x2420` is backed by a capture of our own; every
other row rests on the upstream tables.

Unknown ids decode as `ModelName = "Apple audio device 0x%04X"`, kind `dual`.

### 4.7 Sample packets for the decoder tests

Use the CAPod sample above (AirPods Pro 2 Lightning, `0x1420`, status `0x55`, batteries `0x88`,
flags/case `0xF9`, lid `0x51`). Expected decode: `flipped = (0x55 & 0x20) == 0` → true;
left = high nibble 8 → 80 %, right = low nibble 8 → 80 %; `flags = 0xF` → left charging (0x02),
right charging (0x01), case charging (0x04); case nibble 9 → 90 %; `data[5] & 0x40` set → trust lid;
`lidBit = (0x51 >> 3) & 1 = 0` → OPEN; colour White; state Idle (0x04).

Also add synthetic tests for: length 19 (reject), prefix 0x00 (reject), nibble 0xF (unknown),
nibble 0xC (clamp to 100), `single` kind model, lid bit set with no case bits (Unknown).

### 4.8 Broadcast behaviour

- Cadence while active: roughly 2 frames per second (CAPod sizes its history as "60 = 30 s at fastest
  interval"). RSSI is updated by BlueZ only when it moves by 8 dBm or more.
- The broadcaster uses a **resolvable private address** that rotates. BlueZ creates a new temporary
  `Device1` object per address and removes it 30 s after the last advertisement (`TemporaryTimeout`).
  Never key state on the object path; key on decoded content (§5.3).
- Frames come from whichever pod is "primary". When one pod is out of the case, that pod broadcasts
  with `0x40` clear and a stale lid byte (see 4.5).

---

## 5. Daemon: `oysterd`

Python ≥ 3.11, `dbus-fast` (asyncio), no other runtime dependencies. dbus-fast comes from the
distribution (`python3-dbus-fast` on Fedora and Debian, `python313-dbus_fast` on openSUSE,
`python-dbus-fast` on Arch), from pip, or with the daemon through pipx. The installed service never
uses a venv of its own unless pipx made one.

### 5.1 `scanner.py`: BlueZ discovery session (system bus)

1. Connect `MessageBus(bus_type=BusType.SYSTEM)`. If `org.bluez` has no owner, log it once and wait
   for `NameOwnerChanged` (step 8).
2. Call `org.freedesktop.DBus.ObjectManager.GetManagedObjects` on `/`. Pick the first object with
   `org.bluez.Adapter1` (normally `/org/bluez/hci0`); allow override with `--adapter`.
3. If `Adapter1.Powered` is false, log it once and wait for it (watch `PropertiesChanged`); if there
   is no adapter, wait for `InterfacesAdded`. Do not poll. Only unexpected BlueZ errors are retried
   every 5 s, logged once per distinct error.
4. `Adapter1.SetDiscoveryFilter({"Transport": Variant("s", "le"), "DuplicateData": Variant("b", True)})`.
   A filter is **mandatory**: without one BlueZ only creates objects for discoverable devices and the
   AirPods status beacon carries no Flags AD. `DuplicateData: true` makes BlueZ re-emit
   `ManufacturerData` on every advertisement even when the bytes are unchanged, which the silence
   timeout relies on. Do not set `RSSI` in the filter; filter RSSI in the tracker instead.
5. `Adapter1.StartDiscovery()`. Keep the session open for the lifetime of the daemon.
6. Subscribe with match rules on the system bus:
   - `type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',arg0='org.bluez.Device1'`
   - `type='signal',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesAdded'`
   - `type='signal',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved'`
   - `type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',arg0='org.bluez.Adapter1'`
     (to re-arm when `Discovering` becomes false, for example after `systemctl restart bluetooth`)
7. For each `InterfacesAdded` or `PropertiesChanged` on a `Device1` path: if the changed or initial
   properties contain `ManufacturerData` with key `0x004C`, emit
   `RawFrame(path, address, data: bytes, rssi: int | None, timestamp: float)`. Keep a per-path cache of
   the last RSSI so a `ManufacturerData`-only update still carries a value.
8. On `NameOwnerChanged` for `org.bluez` (bluetoothd restart) go back to step 1.

Power note: the kernel uses an **active** LE scan for discovery. It coexists with the A2DP link but
costs airtime. If audio stutters while scanning, lower `ScanWindowDiscovery` under `[LE]` in
`/etc/bluetooth/main.conf`. This is a documented tuning step, not a code change.

On shutdown `amain` awaits the cancelled tasks and `Scanner.close()` cancels a setup attempt still
in flight, so cleanup runs before `amain` returns. A signal that arrives while a setup attempt is in
flight makes that attempt run again, so no change is lost.

### 5.2 `decoder.py`: pure decoding

```python
@dataclass(frozen=True)
class PodsStatus:
    model_id: int
    model_name: str
    kind: Literal["dual", "single"]
    left_battery: int        # -1 unknown, else 0..100
    right_battery: int
    case_battery: int
    left_charging: bool
    right_charging: bool
    case_charging: bool
    left_in_ear: bool
    right_in_ear: bool
    this_pod_in_case: bool
    one_pod_in_case: bool
    both_pods_in_case: bool
    lid: Literal["open", "closed", "unknown", "not_in_case"]
    lid_counter: int
    colour: str
    conn_state: str
    flipped: bool

def decode(data: bytes) -> PodsStatus | None:   # None = not a valid proximity-pairing frame
```

No I/O, no logging, no asyncio in this module. Everything in §4 is implemented here and nowhere else.

### 5.3 `tracker.py`: ownership, identity, lid state machine

Input: `RawFrame` stream. Output: a single "current device" state plus events.

**Accept a frame when**
- `decode()` succeeds, and
- `allowed_models` is empty (the default: any model) or contains `model_id`, and
- `rssi is None or rssi >= rssi_threshold` (config; default `-70` dBm, loose enough for laptops with
  internal antennas at arm's length; the user can tighten it if strangers trigger the card).

**Fuzzy identity across address rotation.** `identity = (model_id, colour, frozenset({leftNibble,
rightNibble}))`, adapted from CAPod. The case nibble is deliberately left out because it toggles
between unknown and a value as pods go in and out of the case. A frame from the same address as the
current device always counts as the same device. If a frame's identity matches the current device, treat
it as the same device even if the BlueZ path/address changed, for as long as the device is tracked
(until `stale_timeout`). If it
does not match and the current device was seen within the last 2 s, keep the current device and ignore
the newcomer (prefer the one already tracked; log at debug). Otherwise switch to the newcomer.

**Preferring in-case frames.** An untrusted frame (lid `unknown` or `not_in_case`) that arrives within
500 ms of a trusted one from the same device is dropped entirely, because the trusted frame's lid byte
is the one to believe.

**Lid state machine** (per tracked device):

| From | Event | To | Emit |
|---|---|---|---|
| Closed/None | trusted frame, lid = open | Open | `LidOpened`, `StatusChanged` |
| Open | trusted frame, lid = open | Open | `StatusChanged` if any field changed |
| Open | trusted frame, lid = closed | Closed | `LidClosed`, `StatusChanged` |
| Open | no accepted frame for `lid_close_timeout` (2.5 s) | Closed | `LidClosed` |
| Open | untrusted frame (lid unknown / not_in_case) | Open | `StatusChanged` only; do not close |
| any | no frame for `stale_timeout` (15 s) | None | `Present = false`, `StatusChanged` |

`LidOpened` must not re-fire while Open. After `LidClosed`, a new `LidOpened` requires a fresh
trusted open frame; there is no cooldown beyond that.

### 5.4 `service.py`: session-bus interface

Well-known name `io.github.imperriau.Oyster`, object path `/io/github/imperriau/Oyster`, interface
`io.github.imperriau.Oyster.Status1`. Exported with dbus-fast `ServiceInterface`; dbus-fast serves
`org.freedesktop.DBus.Properties` and `Introspectable` automatically.

| Member | Type | Notes |
|---|---|---|
| `Present` | property `b` | a device is tracked and not stale |
| `LidOpen` | property `b` | |
| `Model` | property `q` | model id, 0 when not present |
| `ModelName` | property `s` | |
| `Kind` | property `s` | `dual` or `single` |
| `LeftBattery`, `RightBattery`, `CaseBattery` | property `n` | -1 unknown, else 0..100 |
| `LeftCharging`, `RightCharging`, `CaseCharging` | property `b` | |
| `LeftInEar`, `RightInEar` | property `b` | |
| `Rssi` | property `n` | last RSSI, 0 if unknown |
| `Address` | property `s` | current random address, informational |
| `LastSeen` | property `t` | unix time in milliseconds |
| `GetStatus()` | method `→ a{sv}` | all of the above in one call |
| `LidOpened()` | signal | |
| `LidClosed()` | signal | |
| `StatusChanged()` | signal | emitted after the properties were updated |

Every property change is announced with the standard `PropertiesChanged` on
`org.freedesktop.DBus.Properties`; the daemon batches all fields of one frame into one emission. It
then emits `StatusChanged` if a field other than `LastSeen`/`Rssi` changed (those two go out through
`PropertiesChanged` on every frame), then `LidOpened`/`LidClosed` if applicable. Signals carry no payload on purpose:
the extension reads properties after a signal, so ordering problems cannot leave it with stale data.

### 5.5 CLI and config

`oysterd [--dump] [--debug] [--config PATH] [--rssi N] [--any-model] [--adapter PATH]
[--install-service | --uninstall-service] [--version]`

- `--dump`: do not export the service; print one line per accepted **and** rejected Apple frame:
  timestamp, address, rssi, hex bytes, decode summary or reject reason. The quickest reception check.
- `--debug`: debug-level logs to stderr (journal when under systemd).

Config `~/.config/oyster/config.toml` (all optional):

```toml
rssi_threshold = -70       # dBm; frames weaker than this are ignored
allowed_models = []        # default: any model; e.g. [0x2420] to accept only those
lid_close_timeout = 2.5    # seconds of silence before LidClosed
stale_timeout = 15.0       # seconds before Present=false
adapter = "/org/bluez/hci0"
```

Unknown keys are logged as warnings. Values of the wrong type or out of range are logged as errors
and that key keeps its default. Neither stops the daemon.

### 5.6 Installation, systemd unit and D-Bus activation

The daemon is started on demand. The extension watches `io.github.imperriau.Oyster` with
`Gio.BusNameWatcherFlags.AUTO_START`, the session bus finds the activation file
`io.github.imperriau.Oyster.service` (`SystemdService=oysterd.service`), and systemd starts the unit.
Nothing has to be enabled; `PartOf=graphical-session.target` stops it at logout. Users who want the
daemon without the extension can still `systemctl --user enable oysterd`.

Both files are templates in `daemon/oysterd/data/`, shipped inside the Python package. `@EXEC@`
stands for the path of the `oysterd` command. `oysterd --install-service` fills it with the path of
the command that ran it and writes:

- `$XDG_DATA_HOME/systemd/user/oysterd.service` (default `~/.local/share/...`), and
- `$XDG_DATA_HOME/dbus-1/services/io.github.imperriau.Oyster.service`,

then runs `systemctl --user daemon-reload`, asks the session bus to `ReloadConfig` (dbus-broker and
dbus-daemon only rescan service files then), and restarts the unit. A unit in
`~/.config/systemd/user/` would shadow the installed one; if it is a leftover from an earlier
development install (recognisable by `PYTHONPATH=`) it is disabled and removed, any other unit there
is kept with a warning. `oysterd --uninstall-service` reverses all of it. Distro packages ship the templates
with `@EXEC@` replaced by `/usr/bin/oysterd` under `/usr/lib/systemd/user/` and
`/usr/share/dbus-1/services/` and do not use these flags.

Three ways to get the `oysterd` command, all followed by `oysterd --install-service`:

- `make install-daemon`: copies `daemon/oysterd/` to `~/.local/lib/oyster/` and writes a launcher
  `~/.local/bin/oysterd` that runs it with the system `python3`. No venv, no pip, no build step; the
  checkout can be deleted afterwards. dbus-fast comes from the distribution (`make deps`).
- `pipx install oysterd` (PyPI) or `pipx install ./daemon` from a checkout.
- A distribution package.

The unit is `Type=dbus` with `BusName=io.github.imperriau.Oyster`, so systemd considers it started
once the name is owned. It is sandboxed: `NoNewPrivileges`, `ProtectSystem=strict`,
`ProtectHome=read-only` (the daemon only reads `~/.config/oyster/`), `PrivateTmp`,
`RestrictAddressFamilies=AF_UNIX` (both buses are Unix sockets), `LockPersonality`,
`RestrictRealtime`, `RestrictSUIDSGID`, `SystemCallArchitectures=native`. Verified with systemd 261
in a user session: the options take effect (`NoNewPrivs: 1`, seccomp on, `/home` read-only) and
discovery still runs.

---

## 6. GNOME Shell extension: `oyster@imperriau.github.io`

One code path for GNOME Shell 49, 50 and 51, with no version checks. API facts in this section were
checked against the JavaScript and typelibs of Shell 49.10, 50.6 and 51.0.

### 6.1 `metadata.json`

```json
{
  "uuid": "oyster@imperriau.github.io",
  "name": "Oyster",
  "description": "Requires the companion daemon oysterd, ...: install it first, see <url>#install\n\n...",
  "shell-version": ["49", "50", "51"],
  "url": "https://github.com/imperriau/oyster-gnome",
  "version-name": "0.1.0"
}
```

The description's first sentence says the daemon is required and links to the README's install
section: extensions.gnome.org cannot ship it. `version-name` is set by `tools/version.py` (§7);
EGO assigns its own integer `version`.

No `session-modes` key: the default `["user"]` means the Shell disables the extension on the lock
screen and re-enables it on unlock, so the card can never appear while locked. No settings schema in
0.1 (all tuning lives in the daemon config).

### 6.2 `extension.js`

`enable()` creates the card (§6.4), the daemon notice (§6.3) and the status client, and wires them:

- client appeared → destroy the notice, then sync;
- client changed (any signal or property change) → sync;
- client vanished → hide the card.

Sync calls `card.setModel(Model)` as soon as `Present` is true, so the artwork (including the spin
sheet) is already decoded when the lid opens, then shows the card if `Present && LidOpen` and hides
it otherwise. `disable()` destroys the client, the notice and the card and nulls every field.

Rules from the GNOME review guidelines apply: nothing created in the constructor; everything created
in `enable()` is destroyed in `disable()`; every signal disconnected, every GLib source removed,
`Gio.bus_unwatch_name` called, in-flight async cancelled via a `Gio.Cancellable`, all fields nulled.
Logging goes through `this.getLogger()`. No file I/O blocks the Shell main loop.

### 6.3 `lib/dbusClient.js`

```js
const IFACE_XML = `<node><interface name="io.github.imperriau.Oyster.Status1"> ...properties, signals... </interface></node>`;
const StatusProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

this._cancellable = new Gio.Cancellable();
this._watchId = Gio.bus_watch_name(Gio.BusType.SESSION, 'io.github.imperriau.Oyster',
    Gio.BusNameWatcherFlags.AUTO_START, () => this._connect(), () => this._disconnect());
```

`_connect()` creates `new StatusProxy(Gio.DBus.session, 'io.github.imperriau.Oyster',
'/io/github/imperriau/Oyster', callback, this._cancellable, Gio.DBusProxyFlags.DO_NOT_AUTO_START)`,
then connects `g-properties-changed` and `connectSignal('LidOpened' | 'LidClosed' | 'StatusChanged')`,
all of which call one `onChanged` callback.
`status` is a getter that reads the proxy's cached properties into a plain object. `_disconnect()`
disconnects the signals, drops the proxy and calls `onVanished`. `destroy()` unwatches, cancels, nulls.

**Missing daemon (`lib/daemonNotice.js`).** `enable()` also creates a `DaemonNotice`, which the
extension destroys as soon as the client reports the name appeared. If it is still alive after
10 s, it asks the bus for `ListActivatableNames`. If the name is not activatable (oysterd not
installed), it shows "Oyster needs the oysterd daemon" with an action linking to the README's
`#install`. If it is activatable but did not appear (the unit fails), it shows "the oysterd daemon
did not start" with a link to `#if-the-card-never-appears`. The notification comes from Oyster's
own `MessageTray.Source`, destroyed in `disable()`. A module-level flag limits it to once per
Shell session, because the Shell disables and re-enables extensions around every screen lock.
Verified in the headless Shell for both cases, and that the normal run (daemon present) shows nothing.

### 6.4 `lib/card.js`: the overlay

Modelled on the Shell's own `js/ui/osdWindow.js`, the in-tree bottom-centre OSD.

- `AirPodsCard extends Clutter.Actor` with `x_expand: true, y_expand: true, x_align:
  Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.END, reactive: false`, and a
  `Layout.MonitorConstraint({primary: true})`, which follows monitor changes itself.
- Added with `Main.layoutManager.addTopChrome(this, {trackFullscreen: true})`, so the card sits above
  everything but hides when the monitor has a fullscreen window. The input region follows actor
  reactivity, hence `reactive: false`.
- `trackFullscreen` makes the layout manager own the tracked actor's `visible` flag. The outer actor
  therefore stays visible, and all show, hide and animation happens on an inner `St.BoxLayout`
  (style class `airpods-card`, `orientation: Clutter.Orientation.HORIZONTAL`; never the removed
  `vertical` property). It holds:
  - the artwork (§6.6): left pod, right pod and case side by side, or the spin;
  - a vertical box with the model name (`airpods-card-title`) and three rows, each a `BatteryRing`
    (§6.5), a "Left"/"Right"/"Case" label and a percentage (`–` when unknown).
  For a `single` model the card shows one row labelled "Battery" and no right pod, case row or case
  artwork, whatever `CaseBattery` says: headsets have no case, and their case nibble is not reliably
  "unknown" (the Beats 360 capture has 0). The daemon still publishes the raw value.
- **showCard(status)**: update; if already shown, stop there. Otherwise
  `global.compositor.disable_unredirect()` (so the card paints over unredirected fullscreen
  surfaces, as the OSD does), raise the actor, and ease the box from `opacity 0, translation_y 60`
  to `255, 0` in 300 ms with `EASE_OUT_BACK`. Ring levels animate only while already shown.
- **hideCard()**: ease back out in 220 ms with `EASE_IN_QUAD`; when the transition finishes and no
  show came in between, hide the box, stop the spin and re-enable unredirect.
- Cleanup runs in a `destroy` handler, because the Shell can destroy the actor itself at shutdown
  before `disable()` runs. It cancels artwork loads and re-enables unredirect. No `removeChrome()`
  is needed; the layout manager untracks on `destroy`.

### 6.5 `lib/batteryRing.js`

`BatteryRing extends St.DrawingArea`, registered with `GObject.registerClass` and a GObject property
`value` (double 0..1) so it can be eased with `ease_property('value', v, {duration: 400, mode:
EASE_OUT_QUAD})`, like the Shell's `BarLevel`. `vfunc_repaint()` draws with cairo: a full track
circle, then an arc from 12 o'clock for the level, with round caps.

Everything visual comes from the theme node, so HiDPI scaling follows the theme: size from
`width`/`height`, line width from the `-ring-width` length, colours from `-ring-color` (normal),
`-ring-charging-color` (charging, with a small bolt drawn in the centre), `-ring-low-color` (below
20 %) and `-ring-track-color`. An unknown level draws only a dashed track. Theme node colours are
`Cogl.Color` (there is no `Clutter.Color` since 49) and `cr.setSourceColor` accepts them directly.

### 6.6 `lib/artwork.js` and assets

Each model has an asset directory named by its id as 4 lower-case hex digits (`assets/2420/`), with
`assets/generic/` as the fallback.

- Static parts: `<dir>/{left,right,case}.png`, shown side by side as `St.Icon`s (pods 64, case 120
  logical px; `St.Icon` handles HiDPI). Original placeholder line art at 2× from
  `tools/make_placeholder_art.py`.
- Optional 3D spin: `<dir>/hero.json` and the sprite sheet it names (§6.9). Looked up in the model
  directory only; a generic spin would misrepresent other models. When present it replaces the
  three static parts once decoded.

All lookups are async Gio calls (`query_info_async`, `load_contents_async`); the card fills its
icons when they resolve. A newer `setModel()` cancels the loads of an older one.

### 6.7 `stylesheet.css`

The card: dark translucent background (`rgba(28, 28, 30, 0.94)`), 28 px radius, a faint border and
shadow, `margin-bottom: 64px` so it clears a dock. The rings: 34 px, `-ring-width: 4px`, explicit
white, green, red and track colours rather than the accent colour, so the card looks the same on
every theme. The stylesheet is the single place to change sizes and colours.

### 6.8 GNOME API deltas to respect

- No `Clutter.Container` (use `add_child`/`remove_child`), no `Clutter.Color` (use `Cogl.Color`),
  no `Clutter.Image` (use `St.ImageContent`), no `Meta.Rectangle` (use `Mtk.Rectangle`).
- `St.BoxLayout` takes `orientation:`; 51 removed `vertical`.
- `Gio.DBusProxy.makeProxyWrapper` results are called with `new`. No `Clutter.get_default_backend`.
- Prefer `GLib.timeout_add_once` for one-shot timers; still store the id and remove it in `disable()`.
- `actor.ease()` scales duration by the user's animation setting and accepts `onComplete`/`onStopped`.
- Never import Gtk/Adw in `extension.js`.

### 6.9 3D spin and artwork pipeline

For AirPods Pro 2 (USB-C) the card shows an open case with both pods turning slowly through 360° in a
seamless 4 s loop, instead of the three flat images.

**Asset pipeline.**

1. `tools/blender/airpods_pro2_spin.py` builds an original, simplified case-and-pods scene from
   primitives in Blender (no imported or downloaded models, no Apple renders): rounded base with two
   recesses, lid hinged open at 100°, pods with ear tips, status light, lanyard loop. Cycles on CPU,
   transparent background, AgX view transform with +1.3 exposure, 96 frames at 256×256, starting at
   a three-quarter view. Rendering takes about 3 minutes on a laptop CPU.
2. `tools/pack_spin.py` packs the frames into `extension/assets/2420/hero-sheet.png` (12×8 grid,
   3072×2048, about 3 MB) and writes `hero.json` (`frames`, `columns`, `rows`, `frameWidth`,
   `frameHeight`, `fps`).
3. `make spin` runs both steps; `make spin-preview` renders four angles only. Blender runs as the
   Flathub Flatpak (`flatpak run org.blender.Blender`); override with `BLENDER=blender`. Raw frames
   go to `render/`, which is git-ignored. Only the packed sheet is committed.

All rendered and generated art is CC-BY-SA-4.0 (`extension/assets/LICENSE`). Apple's renders are
copyrighted and must never be added.

**Why one sprite sheet.** 96 separate `St.Icon`s would each load asynchronously on first display, so
the first loop would flicker, and swapping `gicon` per frame goes through the texture cache every
time. One sheet is decoded once and uploaded as one texture; each frame is just a translation.

**`lib/spinView.js`.** `SpinView extends St.Widget`, clipped, fixed size 150 logical px multiplied by
the St theme scale factor. A child `Clutter.Actor` holds an `St.ImageContent` built from a
`GdkPixbuf` with `set_bytes(coglContext, ...)` (the call `ui/screenshot.js` uses; same six arguments
in 49, 50 and 51), with trilinear minification. Frames advance from a `Clutter.Timeline` bound to the
actor, so they follow the frame clock and cost nothing while the card is hidden. With animations
disabled in GNOME settings it shows frame 0 only. The sheet is decoded asynchronously
(`Gio.File.read_async` + `GdkPixbuf.Pixbuf.new_from_stream_async`) with a `Gio.Cancellable`. Until
it is ready, the static parts are shown.

Memory: one 3072×2048 RGBA texture, about 25 MB of GPU memory while the extension is enabled and the
model has been seen. The packed extension zip is about 2.6 MB, almost all of it the sheet.

---

## 7. Install and development workflow

**Makefile targets** (all paths relative to the repo):

| Target | Does |
|---|---|
| `deps` / `deps-pip` | dbus-fast and pytest from the distribution (zypper, dnf, apt-get or pacman), or `pip --user` without sudo |
| `test` | `python3 -m pytest` in `daemon/` |
| `lint-deps` | pinned ruff, mypy and build (`requirements-dev.txt`) into `.venv/`, eslint (`package-lock.json`) into `node_modules/` |
| `lint` / `format` | ruff check and format, `mypy --strict` on the daemon, eslint with `eslint-config-gnome` on the extension, `tools/version.py check`; `format` applies fixes |
| `check` | `lint` + `test`; what CI runs |
| `pack` / `dist` | `gnome-extensions pack` into `dist/` (the EGO upload); `dist` adds the daemon's sdist and wheel |
| `release VERSION=x.y.z` | `tools/version.py set`: writes `__init__.py` and `metadata.json`, dates the changelog's `[Unreleased]` section; pushing tag `vx.y.z` runs `release.yml` |
| `install` / `install-daemon` / `install-extension` | daemon to `~/.local/lib/oyster/` + `~/.local/bin/oysterd` + `oysterd --install-service` (§5.6); extension rsynced to the extensions directory and enabled |
| `uninstall` | reverse of both |
| `status`, `dump`, `logs`, `shell-logs` | state, frame dump, daemon journal, Shell journal |
| `fake`, `headless`, `devkit` | fake daemon, isolated headless Shell test (§8), nested devkit Shell |
| `spin`, `spin-preview` | render and pack the 3D turntable (§6.9) |

**Versioning.** One version number, in `daemon/oysterd/__init__.py`. `pyproject.toml` reads it, and
`tools/version.py` keeps `metadata.json` (`version-name`) and `CHANGELOG.md` in step; `make lint`
fails if they disagree. `release.yml` checks the tag against them, builds the zip, sdist and wheel on
a `v*` tag, attaches them to a GitHub release with notes from the changelog, and uploads to PyPI
through trusted publishing when the repository variable `PUBLISH_PYPI` is `true`.

**Lint notes.** ESLint is pinned to 9 because `eslint-config-gnome` targets it (ESLint 10 flags the
`registerClass(class Foo …)` idiom under `no-shadow`). `service.py` keeps dbus-fast's string
signatures (`-> "b"`) rather than the `Annotated` types of newer dbus-fast, so the `dbus-fast>=2.0`
floor holds; ruff and mypy skip those annotations for that one module.

**Reloading the extension on Wayland.** `Alt+F2 r` does not work on Wayland, and the running Shell
does not see a freshly installed extension, so `gnome-extensions enable` fails the first time.
`tools/enable_extension.py` then appends the uuid to `org.gnome.shell enabled-extensions`; it loads
at the next login. To test changes without logging out, use `make headless` or `make devkit`
(`dbus-run-session -- gnome-shell --devkit --wayland`; `--nested` was removed in 49). Both need
`dbus-run-session` (package `dbus-1-daemon` on openSUSE); `tools/headless-test.sh` also accepts
`DBUS_RUN_SESSION` and `DBUS_DAEMON` paths. The devkit session has its own session bus, so run
`oysterd` or `make fake` inside it. Looking Glass is `Alt+F2 lg`.

**Inspecting the daemon without the extension:**

```
busctl --user introspect io.github.imperriau.Oyster /io/github/imperriau/Oyster
busctl --user monitor io.github.imperriau.Oyster
busctl --user call io.github.imperriau.Oyster /io/github/imperriau/Oyster io.github.imperriau.Oyster.Status1 GetStatus
```

---

## 8. Testing and verification

**Unit tests** (`make test`, CI on Python 3.11 to 3.14): the decoder against the §4.7 sample and
synthetic edge cases, the tracker's identity and lid state machine with a real capture from AirPods
Pro 2 (USB-C), config validation, the scanner's wait-and-retry logic, the CLI, and the service
installer. No hardware needed.

**Headless Shell test** (`make headless`, CI job `headless` on GNOME Shell 49, 50 and 51 in
Fedora containers): starts an isolated headless Shell with the extension and the scripted fake
daemon, takes screenshots and asserts that the card opens, updates and closes, that the
single-battery layout and the spin render, that the card hides when the daemon goes away, that five
disable/enable cycles end enabled, and that the Shell log has no JS errors. In the container it
starts a system bus and removes `/run/systemd/seats`, so the Shell uses its dummy login manager. The
missing-daemon notice was checked in the same harness for both cases (not installed, not starting),
and the packed zip passes the test too.

**Verified on real hardware** (AirPods Pro 2 USB-C, GNOME Shell 50.5, BlueZ 5.87, systemd 261):

- `oysterd --dump` receives the broadcast at about -40 dBm at desk distance.
- Real lid opens and closes produce `LidOpened`/`LidClosed`; the card appears and leaves. In five
  open/close cycles every close came from the lid bit, the 2.5 s silence timeout never fired, and
  the card did not flicker.
- D-Bus activation: `StartServiceByName` starts the unit; uninstalling makes the name
  non-activatable again. The unit's sandboxing takes effect (`NoNewPrivs: 1`, seccomp on, `/home`
  read-only) and discovery still runs.

**Not yet verified:** real AirPods on Shell 49 and 51 (CI uses fake data there); any model other
than `0x2420`; fullscreen hiding (`trackFullscreen`), a second monitor, the lock screen and
`systemctl restart bluetooth` on real hardware. The code paths exist.

**Manual checklist** (before a release, with real AirPods):

1. Open lid at desk distance: card within 0.5 s, levels plausible.
2. Close lid: card gone within 3 s.
3. Open lid, remove one pod: card stays, in-ear/charging flags update, no false close.
4. Put pod back, close lid, reopen: a fresh `LidOpened`, card returns.
5. Walk 5 m away with lid open: card may close on RSSI drop; returning re-opens.
6. `sudo systemctl restart bluetooth` while lid open: daemon recovers, card returns on next frame.
7. `systemctl --user restart oysterd`: card hides on vanish, returns on next open.
8. Toggle the extension off and on: no errors in `journalctl -o cat /usr/bin/gnome-shell`.
9. Fullscreen video playing: card does not appear, and audio does not stutter noticeably.
10. Second monitor attached: card stays on the primary monitor.
11. Lock screen: card never appears while locked.

---

## 9. Risks and open questions

- **Adapter may not receive the broadcast.** Some adapters or firmware filter non-connectable
  advertisements oddly. `oysterd --dump` settles it for a given machine.
- **Active scan cost.** Discovery is an active LE scan for the daemon's lifetime. If it hurts audio or
  battery, the AdvertisementMonitor route (passive scan, §11) fixes it at the cost of
  `Experimental = true` in main.conf.
- **Ownership heuristic.** Same-model AirPods nearby with strong signal will trigger the card. IRK
  matching (§11) is the real fix; until then `allowed_models` and `rssi_threshold` narrow it.
- **Stale lid byte** from the out-of-case pod; handled by trusting only in-case frames, but the first
  frame after opening may come from the wrong pod, so `LidOpened` can lag by one frame.
- **Nibble values above 10** are clamped; the 1 % values in the encrypted payload need §11.
- **GNOME API churn.** Supported range is Shell 49 to 51; expect small fixes at 52.
- **Unverified:** broadcast duration after lid open (no source quantifies it).

---

## 10. Reference code (GPL-3.0, read for reference, not copied)

- LibrePods `linux/ble/blemanager.cpp` (status/battery/lid bit logic, same indexing as §4),
  `android/.../bluetooth/BLEManager.kt` (2.5 s lid-close timeout, 15 s stale),
  `extras/proximity_keys.py` (AAP key retrieval, §11).
- CAPod `pods/core/apple/ble/protocol/ProximityPairing.kt`, `.../devices/DualApplePods.kt`,
  `.../devices/airpods/HasStateDetectionAirPods.kt`, `.../history/PodHistoryRepo.kt` (fuzzy identity),
  `monitor/core/ble/BlePodMonitor.kt` (prefer in-case frames), `app/src/test/.../AirPodsPro2Test.kt`.
- GNOME Shell 50 `js/ui/osdWindow.js` (overlay pattern), `js/ui/barLevel.js` (DrawingArea + eased
  property), maniacx `Bluetooth-Battery-Meter/lib/dbusClient.js` (bus_watch_name pattern).
- BlueZ `doc/org.bluez.Adapter.rst`, `doc/org.bluez.Device.rst`, `src/device.c`
  (`add_manufacturer_data`, DuplicateData semantics).

---

## 11. Future work (not in 0.1)

1. **AdvertisementMonitor1 route**: set `Experimental = true` in `/etc/bluetooth/main.conf`, export an
   ObjectManager root with an `org.bluez.AdvertisementMonitor1` child, `Type = "or_patterns"`,
   `Patterns = [(0, 0xFF, [0x4C, 0x00, 0x07, 0x19])]`, `RegisterMonitor`. Passive scan, lower power.
   Auto-select when the manager interface is present, fall back to discovery otherwise.
2. **Ownership via IRK**: obtain IRK (type 1) and ENC_KEY (type 4) over AAP (L2CAP PSM 0x1001,
   opcode 0x30 request / 0x31 response), requires `DeviceID = bluetooth:004C:0000:0000` in main.conf
   so the AirPods treat the laptop as an Apple host. Resolve the RPA with `ah(irk, prand)`; decrypt
   bytes 11..26 with AES-128-ECB for 1 % battery.
3. 3D spins for more models, a preferences window, show-on-connect, a panel indicator or Quick
   Settings tile, noise-control toggle.
