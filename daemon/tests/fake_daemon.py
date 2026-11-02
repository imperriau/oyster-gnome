#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export io.github.imperriau.Oyster.Status1 with scripted states, for developing the extension.

Usage:
    python3 tests/fake_daemon.py            # loop: open, live updates, close, single-kind, repeat
    python3 tests/fake_daemon.py --open     # open once with a fixed state and stay open
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oysterd.service import StatusService
from oysterd.tracker import empty_props

BASE = dict(
    empty_props(),
    Present=True,
    Model=0x2420,
    ModelName="AirPods Pro 2 (USB-C)",
    Kind="dual",
    LeftBattery=90,
    RightBattery=80,
    CaseBattery=60,
    CaseCharging=True,
    Rssi=-40,
    Address="FA:KE:00:00:00:01",
)


class Fake:
    def __init__(self, svc: StatusService):
        self.svc = svc
        self.state = empty_props()

    def set(self, events=(), **props):
        changed = {k: v for k, v in props.items() if self.state.get(k) != v}
        self.state.update(props)
        out = ["StatusChanged"] if (changed or events) else []
        out += list(events)
        self.svc.publish(changed, out)
        print(
            "state:",
            {
                k: self.state[k]
                for k in ("LidOpen", "LeftBattery", "RightBattery", "CaseBattery", "Kind")
            },
            events,
            flush=True,
        )


async def script(fake: Fake, once_open: bool):
    if once_open:
        fake.set(["LidOpened"], **dict(BASE, LidOpen=True))
        await asyncio.Event().wait()
    while True:
        await asyncio.sleep(2)
        fake.set(["LidOpened"], **dict(BASE, LidOpen=True))
        await asyncio.sleep(2)
        fake.set(
            LeftBattery=100, LeftCharging=True, RightBattery=10, CaseBattery=-1, CaseCharging=False
        )
        await asyncio.sleep(2)
        fake.set(["LidClosed"], LidOpen=False)
        await asyncio.sleep(2)
        fake.set(
            ["LidOpened"],
            **dict(
                BASE,
                LidOpen=True,
                Model=0x1F20,
                ModelName="AirPods Max (USB-C)",
                Kind="single",
                LeftBattery=40,
                RightBattery=-1,
                CaseBattery=0,  # headsets can report a case level (Beats 360 sends 0); not shown
                CaseCharging=False,
            ),
        )
        await asyncio.sleep(2)
        fake.set(["LidClosed"], LidOpen=False)
        await asyncio.sleep(1)
        fake.set(**empty_props())


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--open", action="store_true", help="open once and stay open")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    svc = StatusService()
    await svc.start()
    await script(Fake(svc), args.open)


if __name__ == "__main__":
    asyncio.run(main())
