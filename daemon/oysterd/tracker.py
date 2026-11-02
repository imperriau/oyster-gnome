# SPDX-License-Identifier: GPL-3.0-or-later
"""Ownership filter, fuzzy identity and lid state machine (DESIGN.md §5.3)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Config
from .decoder import PodsStatus, decode
from .scanner import RawFrame

log = logging.getLogger(__name__)

TICK = 0.25  # seconds between timeout checks
SWITCH_GRACE = 2.0  # keep the current device if seen this recently and a stranger appears
PREFER_TRUSTED_WINDOW = 0.5  # ignore untrusted frames right after a trusted one


class Sink(Protocol):
    def publish(self, props: dict[str, Any], events: list[str]) -> None: ...


def empty_props() -> dict[str, Any]:
    return {
        "Present": False,
        "LidOpen": False,
        "Model": 0,
        "ModelName": "",
        "Kind": "",
        "LeftBattery": -1,
        "RightBattery": -1,
        "CaseBattery": -1,
        "LeftCharging": False,
        "RightCharging": False,
        "CaseCharging": False,
        "LeftInEar": False,
        "RightInEar": False,
        "Rssi": 0,
        "Address": "",
        "LastSeen": 0,
    }


Identity = tuple[int, str, frozenset[int]]


def identity(s: PodsStatus) -> Identity:
    """Content-based identity that survives random-address rotation.

    Model + colour + the unordered set of pod nibbles (CAPod-style). The case nibble is left out
    on purpose: it toggles between unknown and a value as pods go in and out of the case.
    """
    return (s.model_id, s.colour, frozenset((s.left_nibble, s.right_nibble)))


@dataclass
class _Current:
    ident: Identity
    address: str
    status: PodsStatus
    last_seen: float  # monotonic
    last_trusted: float  # monotonic, last frame whose lid bit is trustworthy


class Tracker:
    def __init__(
        self,
        cfg: Config,
        sink: Sink,
        clock: Callable[[], float] = time.monotonic,
        wallclock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.cfg = cfg
        self.sink = sink
        self.clock = clock
        self.wallclock_ms = wallclock_ms
        self.current: _Current | None = None
        self.lid_open = False
        self.props = empty_props()

    # ------------------------------------------------------------------ input
    def accepts(self, s: PodsStatus, rssi: int | None) -> bool:
        if self.cfg.allowed_models and s.model_id not in self.cfg.allowed_models:
            return False
        return rssi is None or rssi >= self.cfg.rssi_threshold

    def feed(self, frame: RawFrame) -> None:
        s = decode(frame.data)
        if s is None:
            return
        if not self.accepts(s, frame.rssi):
            log.debug("ignored %s rssi=%s model=0x%04X", frame.address, frame.rssi, s.model_id)
            return
        now = self.clock()
        ident = identity(s)
        cur = self.current

        if cur is not None:
            same = frame.address == cur.address or ident == cur.ident
            if not same:
                if now - cur.last_seen < SWITCH_GRACE:
                    log.debug(
                        "ignoring other device %s while tracking %s", frame.address, cur.address
                    )
                    return
                log.info("switching to device %s (%s)", frame.address, s.model_name)
                if self.lid_open:
                    self._close_lid([])  # silent; the publish below carries the state
                cur = None
            elif not s.lid_trusted and now - cur.last_trusted < PREFER_TRUSTED_WINDOW:
                # A frame from the out-of-case pod right after an in-case frame: skip it.
                cur.last_seen = now
                return

        if cur is None:
            cur = self.current = _Current(ident, frame.address, s, now, 0.0)
        cur.ident, cur.address, cur.status, cur.last_seen = ident, frame.address, s, now
        if s.lid_trusted:
            cur.last_trusted = now

        events: list[str] = []
        if s.lid == "open" and not self.lid_open:
            self.lid_open = True
            events.append("LidOpened")
        elif s.lid == "closed" and self.lid_open:
            self.lid_open = False
            events.append("LidClosed")
        self._publish(s, frame, events)

    # ------------------------------------------------------------------ timeouts
    def tick(self) -> None:
        cur = self.current
        if cur is None:
            return
        idle = self.clock() - cur.last_seen
        if self.lid_open and idle >= self.cfg.lid_close_timeout:
            log.info("no broadcast for %.1f s; treating lid as closed", idle)
            self._close_lid(["LidClosed"], publish=True)
        if idle >= self.cfg.stale_timeout:
            log.info("device %s went stale", cur.address)
            self.current = None
            self.lid_open = False
            self._emit(empty_props(), [])

    async def run(self) -> None:
        while True:
            await asyncio.sleep(TICK)
            try:
                self.tick()
            except Exception:
                log.exception("tracker tick failed")

    # ------------------------------------------------------------------ output
    def _close_lid(self, events: list[str], publish: bool = False) -> None:
        self.lid_open = False
        if publish:
            props = dict(self.props, LidOpen=False)
            self._emit(props, events)

    def _publish(self, s: PodsStatus, frame: RawFrame, events: list[str]) -> None:
        props = {
            "Present": True,
            "LidOpen": self.lid_open,
            "Model": s.model_id,
            "ModelName": s.model_name,
            "Kind": s.kind,
            "LeftBattery": s.left_battery,
            "RightBattery": s.right_battery,
            "CaseBattery": s.case_battery,
            "LeftCharging": s.left_charging,
            "RightCharging": s.right_charging,
            "CaseCharging": s.case_charging,
            "LeftInEar": s.left_in_ear,
            "RightInEar": s.right_in_ear,
            "Rssi": frame.rssi if frame.rssi is not None else self.props.get("Rssi", 0),
            "Address": frame.address,
            "LastSeen": self.wallclock_ms(),
        }
        self._emit(props, events)

    def _emit(self, props: dict[str, Any], events: list[str]) -> None:
        changed = {k: v for k, v in props.items() if self.props.get(k) != v}
        self.props = props
        # LastSeen changes on every frame; only treat it as a change worth StatusChanged
        # when something else changed too, but always publish it.
        significant = [k for k in changed if k not in ("LastSeen", "Rssi")]
        out: list[str] = []
        if significant or events:
            out.append("StatusChanged")
            log.debug("publish %s events=%s", {k: changed[k] for k in significant}, events)
        out.extend(events)
        self.sink.publish(changed, out)
