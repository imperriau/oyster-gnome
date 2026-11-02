# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import logging

from dbus_fast.errors import DBusError

from oysterd import scanner as scanner_mod
from oysterd.scanner import Scanner, _NotReady


class Script:
    """Stand-in for Scanner._start_discovery: raises the queued outcomes in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.hook = None

    async def __call__(self):
        self.calls += 1
        if self.hook:
            self.hook()
        if self.outcomes:
            exc = self.outcomes.pop(0)
            if exc is not None:
                raise exc


def run_setup(sc):
    async def go():
        sc._schedule_setup()
        while sc._setup_task and not sc._setup_task.done():
            await sc._setup_task

    asyncio.run(go())


def mk(*outcomes):
    sc = Scanner(lambda f: None)
    sc._start_discovery = Script(*outcomes)
    return sc


def test_powered_off_logs_once_and_waits(caplog):
    sc = mk(_NotReady("adapter /org/bluez/hci0 is powered off"))
    with caplog.at_level(logging.INFO, logger="oysterd.scanner"):
        run_setup(sc)
        assert sc._start_discovery.calls == 1  # no polling
        sc._start_discovery.outcomes = [_NotReady("adapter /org/bluez/hci0 is powered off")]
        run_setup(sc)  # e.g. an unrelated adapter property changed
    infos = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert len(infos) == 1 and "powered off" in infos[0].getMessage()


def test_no_bluetoothd_waits_for_name_owner(caplog):
    sc = mk(DBusError("org.freedesktop.DBus.Error.ServiceUnknown", "no"))
    with caplog.at_level(logging.INFO, logger="oysterd.scanner"):
        run_setup(sc)
    assert sc._start_discovery.calls == 1
    assert "not running" in caplog.text


def test_signal_during_setup_reruns_it():
    sc = mk(_NotReady("adapter off"), None)
    # Powered=true arrives while the first attempt is still in flight.
    sc._start_discovery.hook = lambda: sc._start_discovery.calls == 1 and sc._schedule_setup()
    run_setup(sc)
    assert sc._start_discovery.calls == 2
    assert sc._problem is None


def test_unexpected_error_retries_on_timer(monkeypatch, caplog):
    monkeypatch.setattr(scanner_mod, "RETRY_DELAY", 0)
    err = DBusError("org.bluez.Error.Failed", "busy")
    sc = mk(err, err, err, None)
    with caplog.at_level(logging.WARNING, logger="oysterd.scanner"):
        run_setup(sc)
    assert sc._start_discovery.calls == 4
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_close_cancels_setup_in_flight():
    class Bus:
        disconnected = False

        def disconnect(self):
            self.disconnected = True

    async def hang():
        await asyncio.Event().wait()

    async def go():
        sc = Scanner(lambda f: None)
        sc._start_discovery = hang
        sc._bus = Bus()
        sc._schedule_setup()
        await asyncio.sleep(0)
        await sc.close()
        return sc

    sc = asyncio.run(go())
    assert sc._setup_task.cancelled()
    assert sc._bus.disconnected
