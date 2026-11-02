# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI entry point: oysterd [--dump] [--debug] ..."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import signal
import sys

from . import __version__
from .config import Config, load_config
from .decoder import DecodeError, decode_or_raise, summary
from .scanner import RawFrame, Scanner

log = logging.getLogger("oysterd")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="oysterd", description=__doc__)
    p.add_argument(
        "--dump",
        action="store_true",
        help="print every Apple frame (accepted and rejected); do not export the service",
    )
    p.add_argument("--debug", action="store_true", help="debug logging")
    p.add_argument("--config", help="config file (default ~/.config/oyster/config.toml)")
    p.add_argument("--rssi", type=int, help="RSSI threshold in dBm (overrides config)")
    p.add_argument("--any-model", action="store_true", help="accept any AirPods/Beats model")
    p.add_argument("--adapter", help="BlueZ adapter object path, e.g. /org/bluez/hci0")
    p.add_argument(
        "--install-service",
        action="store_true",
        help="install the systemd user unit and D-Bus activation file for this oysterd, "
        "start it, and exit",
    )
    p.add_argument(
        "--uninstall-service",
        action="store_true",
        help="stop oysterd, remove its systemd user unit and D-Bus activation file, and exit",
    )
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def dump_frame(frame: RawFrame) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    rssi = "  ?" if frame.rssi is None else f"{frame.rssi:4d}"
    hexdata = frame.data.hex(" ")
    try:
        s = decode_or_raise(frame.data)
        text = summary(s)
    except DecodeError as e:
        text = f"REJECT: {e}"
    print(f"{ts} {frame.address} rssi={rssi} | {hexdata}\n    {text}", flush=True)


async def amain(args: argparse.Namespace, cfg: Config) -> int:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    if args.dump:
        scanner = Scanner(dump_frame, adapter=cfg.adapter)
        tasks = [loop.create_task(scanner.run())]
    else:
        from .service import StatusService
        from .tracker import Tracker

        service = StatusService()
        tracker = Tracker(cfg, service)
        scanner = Scanner(tracker.feed, adapter=cfg.adapter)
        await service.start()
        tasks = [loop.create_task(scanner.run()), loop.create_task(tracker.run())]

    stop_task = loop.create_task(stop.wait())
    done, _ = await asyncio.wait([stop_task, *tasks], return_when=asyncio.FIRST_COMPLETED)
    rc = 0
    for t in done:
        if t is not stop_task and t.exception():
            log.error("fatal: %s", t.exception(), exc_info=t.exception())
            rc = 1
        elif t is not stop_task:
            log.error("system bus connection closed")
            rc = 1
    await scanner.close()
    for t in (stop_task, *tasks):
        t.cancel()
    # Wait for the tasks to unwind so their cleanup runs now, not in asyncio.run()'s teardown.
    await asyncio.gather(stop_task, *tasks, return_exceptions=True)
    return rc


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if args.install_service or args.uninstall_service:
        from .install import InstallError, install_service, uninstall_service

        try:
            if args.install_service:
                install_service(sys.argv[0])
            else:
                uninstall_service()
        except (InstallError, OSError) as e:
            print(f"oysterd: {e}", file=sys.stderr)
            return 1
        return 0
    cfg = load_config(args.config)
    if args.rssi is not None:
        cfg.rssi_threshold = args.rssi
    if args.any_model:
        cfg.allowed_models = []
    if args.adapter:
        cfg.adapter = args.adapter
    return asyncio.run(amain(args, cfg))


if __name__ == "__main__":
    sys.exit(main())
