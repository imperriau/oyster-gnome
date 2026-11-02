# SPDX-License-Identifier: GPL-3.0-or-later
from oysterd.config import Config
from oysterd.scanner import RawFrame
from oysterd.tracker import Tracker

# Real frame captured from the user's AirPods Pro 2 USB-C (pods out of case, music).
OUT_OF_CASE = bytes.fromhex(
    "07190124202199 8f11 0005 ef2043b06dac55b213ee472fda7b8252".replace(" ", "")
)


def mk(status=0x75, batt=0x99, flags_case=0x48, lid=0x51, model=(0x24, 0x20)):
    b = bytearray(OUT_OF_CASE)
    b[3], b[4] = model
    b[5], b[6], b[7], b[8] = status, batt, flags_case, lid
    return bytes(b)


LID_OPEN = mk(lid=0x51)  # this pod in case (0x40), lid bit 0
LID_CLOSED = mk(lid=0x59)  # lid bit 1


class Sink:
    def __init__(self):
        self.events = []
        self.props = {}

    def publish(self, props, events):
        self.props.update(props)
        self.events.extend(events)

    def lid_events(self):
        return [e for e in self.events if e != "StatusChanged"]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def setup(**cfg):
    sink, clock = Sink(), Clock()
    tr = Tracker(Config(**cfg), sink, clock=clock, wallclock_ms=lambda: 42)
    return tr, sink, clock


def feed(tr, data, addr="AA:AA:AA:AA:AA:AA", rssi=-40):
    tr.feed(RawFrame("/org/bluez/hci0/dev_x", addr, data, rssi, 0.0))


def test_open_then_close_by_bit():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN)
    assert sink.lid_events() == ["LidOpened"]
    assert sink.props["LidOpen"] is True and sink.props["Present"] is True
    assert sink.props["LeftBattery"] == 90 and sink.props["CaseBattery"] == 80
    clock.t += 0.5
    feed(tr, LID_OPEN)
    assert sink.lid_events() == ["LidOpened"]  # no re-fire
    clock.t += 0.5
    feed(tr, LID_CLOSED)
    assert sink.lid_events() == ["LidOpened", "LidClosed"]
    assert sink.props["LidOpen"] is False


def test_close_by_silence_and_stale():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN)
    clock.t += 2.0
    tr.tick()
    assert sink.lid_events() == ["LidOpened"]
    clock.t += 0.6
    tr.tick()
    assert sink.lid_events() == ["LidOpened", "LidClosed"]
    clock.t += 13
    tr.tick()
    assert sink.props["Present"] is False
    # re-open after stale
    feed(tr, LID_OPEN)
    assert sink.lid_events()[-1] == "LidOpened"


def test_untrusted_frame_does_not_close():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN)
    clock.t += 1
    feed(tr, mk(status=0x31, lid=0x59))  # out-of-case pod, stale lid byte says closed
    assert sink.lid_events() == ["LidOpened"]
    assert sink.props["LidOpen"] is True


def test_untrusted_right_after_trusted_is_skipped():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN)
    clock.t += 0.1
    feed(tr, mk(status=0x31, batt=0x11))
    assert sink.props["LeftBattery"] == 90


def test_rssi_and_model_filter():
    tr, sink, _ = setup(allowed_models=[0x2420], rssi_threshold=-60)
    feed(tr, LID_OPEN, rssi=-80)
    assert sink.events == []
    feed(tr, mk(model=(0x14, 0x20)))
    assert sink.events == []
    tr2, sink2, _ = setup(allowed_models=[])
    feed(tr2, mk(model=(0x14, 0x20)))
    assert sink2.lid_events() == ["LidOpened"]


def test_defaults_accept_any_model_at_arm_length():
    tr, sink, _ = setup()
    feed(tr, mk(model=(0x14, 0x20)), rssi=-68)
    assert sink.lid_events() == ["LidOpened"]


def test_address_rotation_keeps_device():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN, addr="11:11:11:11:11:11")
    clock.t += 0.5
    feed(tr, LID_OPEN, addr="22:22:22:22:22:22")
    assert sink.lid_events() == ["LidOpened"]
    assert sink.props["Address"] == "22:22:22:22:22:22"


def test_stranger_ignored_while_current_recent():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN, addr="11:11:11:11:11:11")
    clock.t += 0.5
    feed(tr, mk(batt=0x33, lid=0x59), addr="99:99:99:99:99:99")
    assert sink.props["LeftBattery"] == 90
    assert sink.lid_events() == ["LidOpened"]


def test_battery_change_emits_status_changed():
    tr, sink, clock = setup()
    feed(tr, LID_OPEN)
    n = sink.events.count("StatusChanged")
    clock.t += 0.6
    feed(tr, mk(flags_case=0x47))  # case 80 -> 70, same address
    assert sink.events.count("StatusChanged") == n + 1
    assert sink.props["CaseBattery"] == 70
