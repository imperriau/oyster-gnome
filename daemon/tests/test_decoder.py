# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from oysterd.decoder import DecodeError, decode, decode_or_raise, level

# Sample from CAPod AirPodsPro2Test.kt (AirPods Pro 2, Lightning).
CAPOD_SAMPLE = bytes.fromhex(
    "07 19 01 14 20 55 88 F9 51 00 04 20 50 03 CA D5 C9 AC 0F FA 84 78 94 5A 4D DF F5"
)


def frame(**over):
    b = bytearray(CAPOD_SAMPLE)
    for idx, val in over.items():
        b[int(idx[1:])] = val
    return bytes(b)


def test_capod_sample():
    s = decode(CAPOD_SAMPLE)
    assert s is not None
    assert s.model_id == 0x1420
    assert s.model_name == "AirPods Pro 2"
    assert s.flipped is True
    assert s.left_battery == 80 and s.right_battery == 80
    assert s.case_battery == 90
    assert s.left_charging and s.right_charging and s.case_charging
    assert s.this_pod_in_case
    assert s.lid == "open"
    assert s.lid_counter == 1
    assert s.colour == "White"
    assert s.conn_state == "Idle"


def test_beats_360_is_single():
    # Captured frame from CAPod Beats360Test.kt: a headset with one battery (70 %).
    s = decode(
        bytes.fromhex(
            "07 19 01 38 20 00 07 80 04 02 00 01 7D B1 76 1F 5C D6 93 D7 8B 71 77 0A 81 7B AD"
        )
    )
    assert s is not None
    assert s.kind == "single"
    assert s.left_battery == 70
    assert s.right_battery == -1


def test_flip_rule_assigns_nibbles():
    # status with 0x20 set => left is primary, not flipped => left = low nibble.
    s = decode(frame(b5=0x75, b6=0x37))
    assert not s.flipped
    assert s.left_battery == 70 and s.right_battery == 30
    s = decode(frame(b5=0x55, b6=0x37))
    assert s.flipped
    assert s.left_battery == 30 and s.right_battery == 70


def test_charging_flags_follow_flip():
    # flags 0x1 only: not flipped -> left charging; flipped -> right charging
    s = decode(frame(b5=0x75, b7=0x19))
    assert s.left_charging and not s.right_charging and not s.case_charging
    s = decode(frame(b5=0x55, b7=0x19))
    assert s.right_charging and not s.left_charging


def test_lid_closed_bit():
    assert decode(frame(b8=0x59)).lid == "closed"


def test_lid_untrusted_from_out_of_case_pod():
    # Only 0x10 (one pod in case) set, this pod not in case: stale lid byte.
    assert decode(frame(b5=0x31)).lid == "unknown"
    # No case bits at all.
    assert decode(frame(b5=0x2B)).lid == "not_in_case"


def test_both_in_case_trusts_lid():
    assert decode(frame(b5=0x24, b8=0x50)).lid == "open"


def test_in_ear_bits():
    # not flipped (0x20), this pod not in case: xor = False -> left uses 0x02, right 0x08
    s = decode(frame(b5=0x20 | 0x02))
    assert s.left_in_ear and not s.right_in_ear
    s = decode(frame(b5=0x20 | 0x08))
    assert s.right_in_ear and not s.left_in_ear


def test_unknown_and_clamped_nibbles():
    s = decode(frame(b6=0xFC, b7=0x0F))
    assert s.left_battery == -1  # flipped: left = high nibble 0xF
    assert s.right_battery == 100  # 0xC clamped
    assert s.case_battery == -1
    assert level(0) == 0 and level(10) == 100 and level(15) == -1


def test_single_kind_model():
    s = decode(frame(b3=0x0A, b4=0x20, b6=0x06))
    assert s.kind == "single"
    assert s.model_name == "AirPods Max"
    assert s.left_battery == 60
    assert s.right_battery == -1


def test_unknown_model_name():
    s = decode(frame(b3=0x99, b4=0x20))
    assert s.model_name == "Apple audio device 0x9920"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        bytes([0x07]),
        frame(b0=0x10),
        frame(b1=0x13),  # clone length 19
        frame(b2=0x00),  # pairing mode
        CAPOD_SAMPLE[:20],
    ],
)
def test_rejects(data):
    assert decode(data) is None
    with pytest.raises(DecodeError):
        decode_or_raise(data)
