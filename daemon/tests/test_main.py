# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import asyncio
import os
import signal

from oysterd import __main__ as main_mod
from oysterd import service as service_mod
from oysterd import tracker as tracker_mod
from oysterd.config import Config


def install_fakes(monkeypatch, scanner_run):
    """Replace the bus-facing parts of amain; every step is appended to the returned log."""
    log = []

    class FakeScanner:
        def __init__(self, on_frame, adapter=None):
            pass

        async def run(self):
            await scanner_run(log)

        async def close(self):
            log.append("scanner closed")

    class FakeService:
        async def start(self):
            pass

    class FakeTracker:
        def __init__(self, cfg, sink):
            self.feed = lambda frame: None

        async def run(self):
            try:
                await asyncio.Event().wait()
            finally:
                log.append("tracker cleanup")

    monkeypatch.setattr(main_mod, "Scanner", FakeScanner)
    monkeypatch.setattr(service_mod, "StatusService", FakeService)
    monkeypatch.setattr(tracker_mod, "Tracker", FakeTracker)
    return log


def run_amain(log):
    """Return amain's exit code, plus the log and the live tasks at the moment it returned."""

    async def go():
        rc = await main_mod.amain(argparse.Namespace(dump=False), Config())
        return rc, list(log), len(asyncio.all_tasks())

    return asyncio.run(go())


def test_sigterm_waits_for_task_cleanup(monkeypatch):
    async def scanner_run(log):
        asyncio.get_running_loop().call_soon(os.kill, os.getpid(), signal.SIGTERM)
        await asyncio.Event().wait()

    log = install_fakes(monkeypatch, scanner_run)
    rc, at_return, still_running = run_amain(log)
    assert rc == 0
    assert at_return == ["scanner closed", "tracker cleanup"]
    assert still_running == 1  # only amain's own task


def test_fatal_task_error_still_cleans_up(monkeypatch):
    async def scanner_run(log):
        await asyncio.sleep(0)
        raise RuntimeError("system bus gone")

    log = install_fakes(monkeypatch, scanner_run)
    rc, at_return, still_running = run_amain(log)
    assert rc == 1
    assert at_return == ["scanner closed", "tracker cleanup"]
    assert still_running == 1
