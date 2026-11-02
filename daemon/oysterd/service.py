# SPDX-License-Identifier: GPL-3.0-or-later
"""io.github.imperriau.Oyster.Status1 on the session bus (DESIGN.md §5.4).

Note: no `from __future__ import annotations` here; dbus-fast reads the D-Bus type strings from
the annotations at decoration time.
"""

import logging
from typing import Any

from dbus_fast import BusType, PropertyAccess, RequestNameReply, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_property, method, signal

from .tracker import empty_props

log = logging.getLogger(__name__)

BUS_NAME = "io.github.imperriau.Oyster"
OBJECT_PATH = "/io/github/imperriau/Oyster"
INTERFACE = "io.github.imperriau.Oyster.Status1"

SIGNATURES = {
    "Present": "b",
    "LidOpen": "b",
    "Model": "q",
    "ModelName": "s",
    "Kind": "s",
    "LeftBattery": "n",
    "RightBattery": "n",
    "CaseBattery": "n",
    "LeftCharging": "b",
    "RightCharging": "b",
    "CaseCharging": "b",
    "LeftInEar": "b",
    "RightInEar": "b",
    "Rssi": "n",
    "Address": "s",
    "LastSeen": "t",
}


class StatusInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(INTERFACE)
        self.state: dict[str, Any] = empty_props()

    # ---- properties (read-only)
    @dbus_property(access=PropertyAccess.READ)
    def Present(self) -> "b":
        return self.state["Present"]

    @dbus_property(access=PropertyAccess.READ)
    def LidOpen(self) -> "b":
        return self.state["LidOpen"]

    @dbus_property(access=PropertyAccess.READ)
    def Model(self) -> "q":
        return self.state["Model"]

    @dbus_property(access=PropertyAccess.READ)
    def ModelName(self) -> "s":
        return self.state["ModelName"]

    @dbus_property(access=PropertyAccess.READ)
    def Kind(self) -> "s":
        return self.state["Kind"]

    @dbus_property(access=PropertyAccess.READ)
    def LeftBattery(self) -> "n":
        return self.state["LeftBattery"]

    @dbus_property(access=PropertyAccess.READ)
    def RightBattery(self) -> "n":
        return self.state["RightBattery"]

    @dbus_property(access=PropertyAccess.READ)
    def CaseBattery(self) -> "n":
        return self.state["CaseBattery"]

    @dbus_property(access=PropertyAccess.READ)
    def LeftCharging(self) -> "b":
        return self.state["LeftCharging"]

    @dbus_property(access=PropertyAccess.READ)
    def RightCharging(self) -> "b":
        return self.state["RightCharging"]

    @dbus_property(access=PropertyAccess.READ)
    def CaseCharging(self) -> "b":
        return self.state["CaseCharging"]

    @dbus_property(access=PropertyAccess.READ)
    def LeftInEar(self) -> "b":
        return self.state["LeftInEar"]

    @dbus_property(access=PropertyAccess.READ)
    def RightInEar(self) -> "b":
        return self.state["RightInEar"]

    @dbus_property(access=PropertyAccess.READ)
    def Rssi(self) -> "n":
        return self.state["Rssi"]

    @dbus_property(access=PropertyAccess.READ)
    def Address(self) -> "s":
        return self.state["Address"]

    @dbus_property(access=PropertyAccess.READ)
    def LastSeen(self) -> "t":
        return self.state["LastSeen"]

    # ---- methods
    @method()
    def GetStatus(self) -> "a{sv}":
        return {k: Variant(SIGNATURES[k], v) for k, v in self.state.items()}

    # ---- signals (no payload; readers fetch properties)
    @signal()
    def LidOpened(self) -> None:
        return None

    @signal()
    def LidClosed(self) -> None:
        return None

    @signal()
    def StatusChanged(self) -> None:
        return None

    # ---- called by the tracker
    def apply(self, changed: dict[str, Any], events: list[str]) -> None:
        if not changed and not events:
            return
        self.state.update(changed)
        if changed:
            self.emit_properties_changed(changed)
        for ev in events:
            if ev == "StatusChanged":
                self.StatusChanged()
            elif ev in ("LidOpened", "LidClosed"):
                log.info(
                    "%s (%s L=%s R=%s C=%s)",
                    ev,
                    self.state["ModelName"],
                    self.state["LeftBattery"],
                    self.state["RightBattery"],
                    self.state["CaseBattery"],
                )
                getattr(self, ev)()


class StatusService:
    """Owns the session-bus connection and implements the tracker's Sink protocol."""

    def __init__(self) -> None:
        self.iface = StatusInterface()
        self.bus: MessageBus | None = None

    async def start(self) -> None:
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self.bus.export(OBJECT_PATH, self.iface)
        reply = await self.bus.request_name(BUS_NAME)
        if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
            raise RuntimeError(
                f"cannot own {BUS_NAME} on the session bus ({reply}); already running?"
            )
        log.info("exported %s at %s", BUS_NAME, OBJECT_PATH)

    def publish(self, props: dict[str, Any], events: list[str]) -> None:
        self.iface.apply(props, events)
