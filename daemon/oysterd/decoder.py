# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure decoder for Apple proximity-pairing manufacturer data (DESIGN.md §4).

Indices are relative to the start of the Apple manufacturer-data payload, so data[0] == 0x07.
No I/O, no logging, no asyncio here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import COLOUR_TABLE, CONN_STATE_TABLE, Kind, lookup_model

APPLE_COMPANY_ID = 0x004C
MSG_TYPE_PROXIMITY_PAIRING = 0x07
PAYLOAD_LENGTH = 0x19  # 25 bytes follow the length byte
PREFIX_PAIRED = 0x01
FRAME_LENGTH = 2 + PAYLOAD_LENGTH  # 27

Lid = Literal["open", "closed", "unknown", "not_in_case"]


@dataclass(frozen=True)
class PodsStatus:
    model_id: int
    model_name: str
    kind: Kind
    left_battery: int  # -1 unknown, else 0..100
    right_battery: int
    case_battery: int
    left_charging: bool
    right_charging: bool
    case_charging: bool
    left_in_ear: bool
    right_in_ear: bool
    this_pod_in_case: bool
    one_pod_in_case: bool
    both_pods_in_case: bool
    lid: Lid
    lid_counter: int
    colour: str
    conn_state: str
    flipped: bool
    # Raw nibbles, used for the tracker's fuzzy identity.
    left_nibble: int
    right_nibble: int
    case_nibble: int

    @property
    def lid_trusted(self) -> bool:
        return self.lid in ("open", "closed")


class DecodeError(ValueError):
    """Raised by decode_or_raise() with a human-readable reject reason."""


def level(nibble: int) -> int:
    """Map a battery nibble to a percentage: 0xF unknown (-1), clamp >10 to 100."""
    if nibble == 0xF:
        return -1
    return min(nibble, 10) * 10


def decode_or_raise(data: bytes) -> PodsStatus:
    if len(data) < 2:
        raise DecodeError(f"too short ({len(data)} bytes)")
    if data[0] != MSG_TYPE_PROXIMITY_PAIRING:
        raise DecodeError(f"not proximity pairing (type 0x{data[0]:02X})")
    if data[1] != PAYLOAD_LENGTH:
        raise DecodeError(f"unexpected length byte 0x{data[1]:02X}")
    if len(data) < FRAME_LENGTH:
        raise DecodeError(f"truncated ({len(data)} bytes)")
    if data[2] != PREFIX_PAIRED:
        raise DecodeError(f"prefix 0x{data[2]:02X} (pairing mode or unknown)")

    model_id = (data[3] << 8) | data[4]
    info = lookup_model(model_id)

    status = data[5]
    flipped = (status & 0x20) == 0
    this_in_case = bool(status & 0x40)
    one_in_case = bool(status & 0x10)
    both_in_case = bool(status & 0x04)
    xor = flipped ^ this_in_case
    left_in_ear = bool(status & 0x08) if xor else bool(status & 0x02)
    right_in_ear = bool(status & 0x02) if xor else bool(status & 0x08)

    b6 = data[6]
    hi, lo = (b6 >> 4) & 0xF, b6 & 0xF
    if info.kind == "single":
        left_nib, right_nib = lo, 0xF
    elif flipped:
        left_nib, right_nib = hi, lo
    else:
        left_nib, right_nib = lo, hi

    flags = (data[7] >> 4) & 0xF
    case_nib = data[7] & 0xF
    if flipped:
        right_chg, left_chg = bool(flags & 0x01), bool(flags & 0x02)
    else:
        right_chg, left_chg = bool(flags & 0x02), bool(flags & 0x01)
    case_chg = bool(flags & 0x04)
    if info.kind == "single":
        left_chg = left_chg or right_chg
        right_chg = False

    lid_byte = data[8]
    lid_counter = lid_byte & 0x07
    lid_bit = (lid_byte >> 3) & 0x01
    lid: Lid
    if this_in_case or both_in_case:
        lid = "closed" if lid_bit else "open"
    elif not one_in_case:
        lid = "not_in_case"
    else:
        lid = "unknown"

    return PodsStatus(
        model_id=model_id,
        model_name=info.name,
        kind=info.kind,
        left_battery=level(left_nib),
        right_battery=level(right_nib),
        case_battery=level(case_nib),
        left_charging=left_chg,
        right_charging=right_chg,
        case_charging=case_chg,
        left_in_ear=left_in_ear,
        right_in_ear=right_in_ear,
        this_pod_in_case=this_in_case,
        one_pod_in_case=one_in_case,
        both_pods_in_case=both_in_case,
        lid=lid,
        lid_counter=lid_counter,
        colour=COLOUR_TABLE.get(data[9], f"0x{data[9]:02X}"),
        conn_state=CONN_STATE_TABLE.get(data[10], f"0x{data[10]:02X}"),
        flipped=flipped,
        left_nibble=left_nib,
        right_nibble=right_nib,
        case_nibble=case_nib,
    )


def decode(data: bytes) -> PodsStatus | None:
    """Decode a proximity-pairing frame; return None if it is not a valid one."""
    try:
        return decode_or_raise(data)
    except DecodeError:
        return None


def summary(s: PodsStatus) -> str:
    def pct(v: int, chg: bool) -> str:
        return ("?" if v < 0 else f"{v}%") + ("+" if chg else "")

    return (
        f"{s.model_name} [0x{s.model_id:04X}] L={pct(s.left_battery, s.left_charging)} "
        f"R={pct(s.right_battery, s.right_charging)} C={pct(s.case_battery, s.case_charging)} "
        f"lid={s.lid} inEar={'L' if s.left_in_ear else ''}{'R' if s.right_in_ear else ''} "
        f"case={'this' if s.this_pod_in_case else ''}{'one' if s.one_pod_in_case else ''}"
        f"{'both' if s.both_pods_in_case else ''} colour={s.colour} state={s.conn_state}"
    )
