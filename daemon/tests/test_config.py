# SPDX-License-Identifier: GPL-3.0-or-later
import logging

from oysterd.config import Config, load_config


def write(tmp_path, text):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml") == Config()


def test_defaults_accept_any_model():
    cfg = Config()
    assert cfg.allowed_models == [] and cfg.rssi_threshold == -70


def test_valid_keys(tmp_path):
    cfg = load_config(
        write(
            tmp_path,
            """
rssi_threshold = -55
allowed_models = [0x2420, 0x1420]
lid_close_timeout = 3
stale_timeout = 20.5
adapter = "/org/bluez/hci1"
""",
        )
    )
    assert cfg == Config(-55, [0x2420, 0x1420], 3.0, 20.5, "/org/bluez/hci1")
    assert isinstance(cfg.lid_close_timeout, float)


def test_unknown_key_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        cfg = load_config(write(tmp_path, "rssi_treshold = -50\nhistory_timeout = 30\n"))
    assert cfg == Config()
    assert "unknown key 'rssi_treshold'" in caplog.text
    assert "unknown key 'history_timeout'" in caplog.text


def test_bad_values_keep_defaults(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        cfg = load_config(
            write(
                tmp_path,
                """
rssi_threshold = "-50"
allowed_models = 0x2420
lid_close_timeout = -1
stale_timeout = true
adapter = "hci0"
""",
            )
        )
    assert cfg == Config()
    for key in (
        "rssi_threshold",
        "allowed_models",
        "lid_close_timeout",
        "stale_timeout",
        "adapter",
    ):
        assert f": {key}: " in caplog.text


def test_bad_value_does_not_spoil_good_ones(tmp_path):
    cfg = load_config(write(tmp_path, "rssi_threshold = -50\nallowed_models = [0x2420, 70000]\n"))
    assert cfg.rssi_threshold == -50 and cfg.allowed_models == []


def test_broken_toml_gives_defaults(tmp_path):
    assert load_config(write(tmp_path, "rssi_threshold = = 1")) == Config()
