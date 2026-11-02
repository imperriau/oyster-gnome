# SPDX-License-Identifier: GPL-3.0-or-later
"""BlueZ LE discovery session on the system bus (DESIGN.md §5.1).

Emits a RawFrame for every Apple (0x004C) manufacturer-data advertisement BlueZ reports.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError

from .decoder import APPLE_COMPANY_ID

log = logging.getLogger(__name__)

BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"

MATCH_RULES = [
    f"type='signal',sender='{BLUEZ}',interface='{PROPS_IFACE}',member='PropertiesChanged',arg0='{DEVICE_IFACE}'",
    f"type='signal',sender='{BLUEZ}',interface='{PROPS_IFACE}',member='PropertiesChanged',arg0='{ADAPTER_IFACE}'",
    f"type='signal',sender='{BLUEZ}',interface='{OM_IFACE}',member='InterfacesAdded'",
    f"type='signal',sender='{BLUEZ}',interface='{OM_IFACE}',member='InterfacesRemoved'",
    "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
    f"member='NameOwnerChanged',arg0='{BLUEZ}'",
]

# Errors meaning bluetoothd is not on the bus; NameOwnerChanged tells us when it arrives.
NO_BLUEZ_ERRORS = (
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
)
RETRY_DELAY = 5.0


@dataclass(frozen=True)
class RawFrame:
    path: str
    address: str
    data: bytes
    rssi: int | None
    timestamp: float


def _unwrap(v: Any) -> Any:
    return v.value if isinstance(v, Variant) else v


def _address_from_path(path: str) -> str:
    tail = path.rsplit("/", 1)[-1]
    if tail.startswith("dev_"):
        return tail[4:].replace("_", ":")
    return tail


class Scanner:
    def __init__(self, on_frame: Callable[[RawFrame], None], adapter: str | None = None) -> None:
        self._on_frame = on_frame
        self._adapter_override = adapter
        self._adapter: str | None = None
        self._bus: MessageBus | None = None
        self._rssi: dict[str, int] = {}
        self._addr: dict[str, str] = {}
        self._setup_lock = asyncio.Lock()
        self._setup_task: asyncio.Task[None] | None = None
        self._setup_again = False
        self._problem: str | None = None  # last setup problem logged, to log each one once
        self._stopped = asyncio.Event()

    # ---------------------------------------------------------------- lifecycle
    async def run(self) -> None:
        """Connect and keep a discovery session alive until the bus disconnects."""
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._bus.add_message_handler(self._on_message)
        for rule in MATCH_RULES:
            await self._call(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "AddMatch",
                "s",
                [rule],
            )
        self._schedule_setup()
        await self._bus.wait_for_disconnect()

    async def close(self) -> None:
        if self._bus is None:
            return
        if self._setup_task:
            self._setup_task.cancel()
            await asyncio.gather(self._setup_task, return_exceptions=True)
        if self._adapter:
            with contextlib.suppress(Exception):  # best effort on shutdown
                await self._call(BLUEZ, self._adapter, ADAPTER_IFACE, "StopDiscovery")
        self._bus.disconnect()

    # ---------------------------------------------------------------- D-Bus helpers
    async def _call(
        self,
        dest: str,
        path: str,
        iface: str,
        member: str,
        signature: str = "",
        body: list[Any] | None = None,
    ) -> list[Any]:
        assert self._bus is not None
        reply = await self._bus.call(
            Message(
                destination=dest,
                path=path,
                interface=iface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise DBusError(
                reply.error_name or "org.freedesktop.DBus.Error.Failed",
                (reply.body or [""])[0],
                reply,
            )
        return reply.body

    def _schedule_setup(self, delay: float = 0.0) -> None:
        if self._setup_task and not self._setup_task.done():
            # A signal arrived while setup runs; its outcome may already be stale.
            self._setup_again = True
            return
        self._setup_task = asyncio.get_running_loop().create_task(self._setup(delay))

    async def _setup(self, delay: float) -> None:
        """Start discovery, or wait for the BlueZ signal that makes it possible.

        Not-ready states (no adapter, adapter off, no bluetoothd) are logged once and then left to
        InterfacesAdded, PropertiesChanged(Powered) and NameOwnerChanged, which call
        _schedule_setup() again. Only unexpected BlueZ errors are retried on a timer.
        """
        if delay:
            await asyncio.sleep(delay)
        async with self._setup_lock:
            while True:
                self._setup_again = False
                try:
                    await self._start_discovery()
                    self._problem = None
                except _NotReady as e:
                    self._report(f"{e}; waiting for BlueZ to report a change", logging.INFO)
                except DBusError as e:
                    if e.type in NO_BLUEZ_ERRORS:
                        self._report(
                            "bluetoothd is not running; waiting for it to start", logging.INFO
                        )
                    else:
                        self._report(
                            f"BlueZ setup failed ({e.type}: {e.text}); retrying every "
                            f"{RETRY_DELAY:g} s",
                            logging.WARNING,
                        )
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                if not self._setup_again:
                    return

    def _report(self, problem: str, level: int) -> None:
        """Log a setup problem the first time it occurs; repeats go to debug."""
        log.log(level if problem != self._problem else logging.DEBUG, "%s", problem)
        self._problem = problem

    async def _start_discovery(self) -> None:
        (objects,) = await self._call(BLUEZ, "/", OM_IFACE, "GetManagedObjects")
        adapter = None
        for path, ifaces in sorted(objects.items()):
            if (
                adapter is None
                and ADAPTER_IFACE in ifaces
                and self._adapter_override in (None, path)
            ):
                adapter = (path, ifaces[ADAPTER_IFACE])
            if DEVICE_IFACE in ifaces:
                self._remember_device(path, ifaces[DEVICE_IFACE], emit=False)
        if adapter is None:
            raise _NotReady("no Bluetooth adapter found")
        path, props = adapter
        self._adapter = path
        if not _unwrap(props.get("Powered", False)):
            raise _NotReady(f"adapter {path} is powered off")
        await self._call(
            BLUEZ,
            path,
            ADAPTER_IFACE,
            "SetDiscoveryFilter",
            "a{sv}",
            [
                {
                    "Transport": Variant("s", "le"),
                    "DuplicateData": Variant("b", True),
                }
            ],
        )
        try:
            await self._call(BLUEZ, path, ADAPTER_IFACE, "StartDiscovery")
        except DBusError as e:
            if e.type != "org.bluez.Error.InProgress":
                raise
        log.info("LE discovery running on %s", path)

    # ---------------------------------------------------------------- signal handling
    def _on_message(self, msg: Message) -> bool:
        if msg.message_type != MessageType.SIGNAL or msg.path is None:
            return False
        try:
            if msg.member == "PropertiesChanged" and msg.interface == PROPS_IFACE:
                iface, changed, _inval = msg.body
                if iface == DEVICE_IFACE:
                    self._remember_device(msg.path, changed, emit=True)
                elif iface == ADAPTER_IFACE and msg.path == self._adapter:
                    self._on_adapter_changed(changed)
            elif msg.member == "InterfacesAdded":
                path, ifaces = msg.body
                if DEVICE_IFACE in ifaces:
                    self._remember_device(path, ifaces[DEVICE_IFACE], emit=True)
                elif ADAPTER_IFACE in ifaces and self._adapter is None:
                    self._schedule_setup()
            elif msg.member == "InterfacesRemoved":
                path, ifaces = msg.body
                if DEVICE_IFACE in ifaces:
                    self._rssi.pop(path, None)
                    self._addr.pop(path, None)
                if ADAPTER_IFACE in ifaces and path == self._adapter:
                    log.warning("adapter %s removed", path)
                    self._adapter = None
            elif msg.member == "NameOwnerChanged":
                _name, _old, new = msg.body
                if new:
                    log.info("bluetoothd (re)started; re-arming discovery")
                    self._rssi.clear()
                    self._addr.clear()
                    self._schedule_setup(delay=1.0)
                else:
                    log.warning("bluetoothd went away")
                    self._adapter = None
        except Exception:  # never let a bad signal kill the bus loop
            log.exception("error handling %s", msg.member)
        return False

    def _on_adapter_changed(self, changed: dict[str, Any]) -> None:
        if "Powered" in changed and _unwrap(changed["Powered"]):
            log.info("adapter powered on; re-arming discovery")
            self._schedule_setup(delay=0.5)
        elif "Discovering" in changed and not _unwrap(changed["Discovering"]):
            log.info("discovery stopped; re-arming")
            self._schedule_setup(delay=1.0)

    def _remember_device(self, path: str, props: dict[str, Any], emit: bool) -> None:
        if "Address" in props:
            self._addr[path] = _unwrap(props["Address"])
        if "RSSI" in props:
            self._rssi[path] = int(_unwrap(props["RSSI"]))
        if not emit or "ManufacturerData" not in props:
            return
        mdata = _unwrap(props["ManufacturerData"])
        payload = mdata.get(APPLE_COMPANY_ID)
        if payload is None:
            return
        self._on_frame(
            RawFrame(
                path=path,
                address=self._addr.get(path) or _address_from_path(path),
                data=bytes(_unwrap(payload)),
                rssi=self._rssi.get(path),
                timestamp=time.monotonic(),
            )
        )


class _NotReady(Exception):
    pass
