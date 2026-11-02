# SPDX-License-Identifier: GPL-3.0-or-later
import configparser

import pytest

from oysterd import install
from oysterd.install import InstallError


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


class Recorder:
    def __init__(self, rc=0):
        self.cmds, self.rc = [], rc

    def __call__(self, cmd):
        self.cmds.append(cmd)
        return self.rc


def ini(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    cp.read(path)
    return cp


def test_exec_path_rejects_module_invocation():
    with pytest.raises(InstallError, match="python3 -m"):
        install.exec_path("/repo/daemon/oysterd/__main__.py")
    with pytest.raises(InstallError, match="whitespace"):
        install.exec_path("/home/a b/.local/bin/oysterd")
    assert install.exec_path("/usr/bin/oysterd") == "/usr/bin/oysterd"


def test_install_writes_both_files_and_starts(xdg):
    run = Recorder()
    install.install_service("/opt/x/bin/oysterd", run=run)

    unit = ini(install.unit_path())
    assert unit["Service"]["ExecStart"] == "/opt/x/bin/oysterd"
    assert unit["Service"]["BusName"] == "io.github.imperriau.Oyster"
    assert unit["Service"]["Type"] == "dbus"

    svc = ini(install.dbus_service_path())["D-BUS Service"]
    assert svc["Name"] == "io.github.imperriau.Oyster"
    assert svc["Exec"] == "/opt/x/bin/oysterd"
    assert svc["SystemdService"] == "oysterd.service"

    assert ["systemctl", "--user", "daemon-reload"] in run.cmds
    assert any("ReloadConfig" in c for c in run.cmds)
    assert run.cmds[-1] == ["systemctl", "--user", "restart", "oysterd.service"]


def test_install_replaces_legacy_checkout_unit(xdg):
    legacy = install.admin_unit_path()
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[Service]\nEnvironment=PYTHONPATH=/repo/daemon\n")
    run = Recorder()
    install.install_service("/usr/bin/oysterd", run=run)
    assert not legacy.exists()
    assert run.cmds[0] == ["systemctl", "--user", "disable", "--now", "oysterd.service"]


def test_install_keeps_admin_override(xdg, capsys):
    admin = install.admin_unit_path()
    admin.parent.mkdir(parents=True)
    admin.write_text("[Service]\nExecStart=/custom\n")
    install.install_service("/usr/bin/oysterd", run=Recorder())
    assert admin.exists()
    assert "overrides" in capsys.readouterr().out


def test_install_survives_missing_systemd(xdg, capsys):
    install.install_service("/usr/bin/oysterd", run=Recorder(rc=127))
    assert install.unit_path().exists()
    assert "warning" in capsys.readouterr().out


def test_uninstall_removes_files(xdg):
    install.install_service("/usr/bin/oysterd", run=Recorder())
    run = Recorder()
    install.uninstall_service(run=run)
    assert not install.unit_path().exists() and not install.dbus_service_path().exists()
    assert run.cmds[0] == ["systemctl", "--user", "disable", "--now", "oysterd.service"]


def test_uninstall_when_not_installed_is_quiet(xdg):
    run = Recorder()
    install.uninstall_service(run=run)
    assert ["systemctl", "--user", "disable", "--now", "oysterd.service"] not in run.cmds
