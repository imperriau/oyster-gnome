# SPDX-License-Identifier: GPL-3.0-or-later
"""TOML config with defaults (DESIGN.md §5.5)."""

from __future__ import annotations

import logging
import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "oyster" / "config.toml"
)


@dataclass
class Config:
    rssi_threshold: int = -70
    allowed_models: list[int] = field(default_factory=list)  # empty = any model
    lid_close_timeout: float = 2.5
    stale_timeout: float = 15.0
    adapter: str | None = None


class ConfigError(ValueError):
    pass


def _int(v: Any, lo: int, hi: int) -> int:
    # bool is an int subclass; `rssi_threshold = true` is a mistake, not 1.
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"expected an integer, got {v!r}")
    if not lo <= v <= hi:
        raise ConfigError(f"{v} is outside {lo}..{hi}")
    return v


def _rssi(v: Any) -> int:
    return _int(v, -127, 20)


def _seconds(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"expected a number of seconds, got {v!r}")
    if v <= 0:
        raise ConfigError(f"expected a positive number of seconds, got {v}")
    return float(v)


def _models(v: Any) -> list[int]:
    if not isinstance(v, list):
        raise ConfigError(f"expected a list of model ids such as [0x2420], got {v!r}")
    return [_int(m, 0, 0xFFFF) for m in v]


def _adapter(v: Any) -> str:
    if not isinstance(v, str) or not v.startswith("/org/bluez/"):
        raise ConfigError(f'expected a BlueZ adapter path such as "/org/bluez/hci0", got {v!r}')
    return v


_KEYS: dict[str, Callable[[Any], Any]] = {
    "rssi_threshold": _rssi,
    "allowed_models": _models,
    "lid_close_timeout": _seconds,
    "stale_timeout": _seconds,
    "adapter": _adapter,
}


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Read the config file. Bad or unknown keys are logged and skipped, never fatal."""
    cfg = Config()
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        if path:
            log.warning("config %s not found; using defaults", p)
        return cfg
    try:
        with p.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        log.error("cannot read config %s: %s; using defaults", p, e)
        return cfg
    for key, value in data.items():
        check = _KEYS.get(key)
        if check is None:
            log.warning("config %s: unknown key %r ignored (known: %s)", p, key, ", ".join(_KEYS))
            continue
        try:
            setattr(cfg, key, check(value))
        except ConfigError as e:
            log.error("config %s: %s: %s; keeping default %r", p, key, e, getattr(cfg, key))
    log.info("loaded config %s", p)
    return cfg
