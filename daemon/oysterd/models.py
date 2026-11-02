# SPDX-License-Identifier: GPL-3.0-or-later
"""Static lookup tables for the Apple proximity-pairing message (DESIGN.md §4)."""

from __future__ import annotations

from typing import Literal, NamedTuple

Kind = Literal["dual", "single"]


class ModelInfo(NamedTuple):
    name: str
    kind: Kind


# Model ids and kinds, checked 2026-10-29 against these tables. Each row lists the ones that have
# its exact id; "kind" follows CAPod (DualApplePods or SingleApplePods), the only source that
# records it for every row.
#   C  CAPod             d4rken-org/capod @ b6c3208 (2026-10-28), DEVICE_CODE in
#                        app/src/main/java/eu/darken/capod/pods/core/apple/ble/devices/*/*.kt
#   L  LibrePods         librepods-org/librepods @ 89356c0 (2026-10-16), linux/ble/blemanager.cpp
#   O  OpenPods          adolfintel/OpenPods @ 9cd8008 (2025-09-26), PodsStatus.java (full-id
#                        matches only; its one-nibble matches are not counted)
#   F  continuity        furiousMAC/continuity @ d9fa98b (2025-08-28),
#                        dissector/4.4.0/packet-bthci_cmd.c airpods_device_vals[]
#   D  AirPodsDesktop    SpriteOvO/AirPodsDesktop @ 56b0400 (2026-09-19), Source/Core/AppleCP.cpp
#                        (ids written byte-swapped: 0x2024 there is 0x2420 here)
#   M  MagicPodsCore     steam3d/MagicPodsCore @ 04af4bd (2026-10-27),
#                        src/sdk/aap/enums/AapModelIds.h (Device ID product ids, byte-swapped)
# Rows tagged only "C M" have the least independent backing. A frame capture from a real device
# (the "Model support" issue template asks for one) is what confirms or corrects a row.
MODEL_TABLE: dict[int, ModelInfo] = {
    0x0220: ModelInfo("AirPods (1st gen)", "dual"),  # C L O F D M
    0x0F20: ModelInfo("AirPods (2nd gen)", "dual"),  # C L O F D M
    0x1320: ModelInfo("AirPods (3rd gen)", "dual"),  # C L O D M
    0x1920: ModelInfo("AirPods 4", "dual"),  # C L D M
    0x1B20: ModelInfo("AirPods 4 (ANC)", "dual"),  # C L D M
    0x3620: ModelInfo("AirPods (5th gen)", "dual"),  # C D M
    0x3020: ModelInfo("AirPods (5th gen, wireless case)", "dual"),  # C D M
    0x0E20: ModelInfo("AirPods Pro", "dual"),  # C L O F D M
    0x1420: ModelInfo("AirPods Pro 2", "dual"),  # C L O D M
    0x2420: ModelInfo("AirPods Pro 2 (USB-C)", "dual"),  # C L O D M, Oyster capture
    0x2720: ModelInfo("AirPods Pro 3", "dual"),  # C O D M
    0x0A20: ModelInfo("AirPods Max", "single"),  # C L D M
    0x1F20: ModelInfo("AirPods Max (USB-C)", "single"),  # C L D M
    0x2D20: ModelInfo("AirPods Max 2", "single"),  # C M
    0x0320: ModelInfo("Powerbeats 3", "single"),  # C O F M
    0x0520: ModelInfo("BeatsX", "single"),  # C O F M
    0x0620: ModelInfo("Beats Solo 3", "single"),  # C O F M
    0x0920: ModelInfo("Beats Studio 3", "single"),  # C M
    0x0B20: ModelInfo("Powerbeats Pro", "dual"),  # C M
    0x0C20: ModelInfo("Beats Solo Pro", "single"),  # C M
    0x0D20: ModelInfo("Powerbeats 4", "single"),  # C M
    0x1020: ModelInfo("Beats Flex", "single"),  # C O M
    0x1120: ModelInfo("Beats Studio Buds", "dual"),  # C M
    0x1220: ModelInfo("Beats Fit Pro", "dual"),  # C D M
    0x1620: ModelInfo("Beats Studio Buds+", "dual"),  # C M
    0x1720: ModelInfo("Beats Studio Pro", "single"),  # C M
    0x1D20: ModelInfo("Powerbeats Pro 2", "dual"),  # C M
    0x2520: ModelInfo("Beats Solo 4", "single"),  # C M
    0x2620: ModelInfo("Beats Solo Buds", "dual"),  # C M
    0x3820: ModelInfo("Beats 360", "single"),  # C M; single per CAPod's captured frame
}

COLOUR_TABLE: dict[int, str] = {
    0x00: "White",
    0x01: "Black",
    0x02: "Red",
    0x03: "Blue",
    0x04: "Pink",
    0x05: "Gray",
    0x06: "Silver",
    0x07: "Gold",
    0x08: "Rose Gold",
    0x09: "Space Gray",
    0x0A: "Dark Blue",
    0x0B: "Light Blue",
    0x0C: "Yellow",
}

CONN_STATE_TABLE: dict[int, str] = {
    0x00: "Disconnected",
    0x04: "Idle",
    0x05: "Music",
    0x06: "Call",
    0x07: "Ringing",
    0x09: "Hanging up",
}


def lookup_model(model_id: int) -> ModelInfo:
    info = MODEL_TABLE.get(model_id)
    if info is None:
        return ModelInfo(f"Apple audio device 0x{model_id:04X}", "dual")
    return info
