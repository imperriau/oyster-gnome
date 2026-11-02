# Prior art

Oyster does one thing: the "case opened" card, from the Bluetooth LE broadcast, on GNOME. Other
projects cover the rest of the AirPods-on-other-platforms story, and several of them taught us the
protocol. If you need something Oyster does not do, one of these probably does.

| Project | Platform | Lid-open popup | Focus |
|---|---|---|---|
| [LibrePods](https://github.com/librepods-org/librepods) | Linux, Android | No | Direct connection over Apple's accessory protocol: exact battery, noise control, ear detection, conversational awareness |
| [CAPod](https://github.com/d4rken-org/capod) | Android | Yes | Battery from the BLE broadcast, popup when the case opens, auto-connect |
| [OpenPods](https://github.com/adolfintel/OpenPods) | Android | No | Battery from the BLE broadcast in a notification while connected |
| [Bluetooth Battery Meter](https://github.com/maniacx/Bluetooth-Battery-Meter) | GNOME Shell | No | Battery of Bluetooth devices in the Shell; AirPods features through its BudsLink companion app |
| [MagicPods](https://github.com/steam3d/MagicPods-Windows) | Windows | Yes | iOS-style popup animation, tray battery, noise control, hotkeys |
| [AirPodsDesktop](https://github.com/SpriteOvO/AirPodsDesktop) | Windows | Yes | Animated device popups, battery |

## Where Oyster differs

- It runs on GNOME Shell and draws the card as part of the Shell, so it can slide in over every
  window on Wayland, which a normal app cannot do.
- It needs no connection and no change to `/etc/bluetooth/main.conf`. The price is 10 % battery
  steps and a heuristic, rather than cryptographic, check that the AirPods are yours.
- The daemon publishes the decoded state on the session bus, so other frontends can use it.

For exact battery levels and noise control on Linux, use LibrePods.
