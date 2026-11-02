# SPDX-License-Identifier: GPL-3.0-or-later
# Oyster: see DESIGN.md §7.
REPO        := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
UUID        := oyster@imperriau.github.io
EXT_DIR     := $(HOME)/.local/share/gnome-shell/extensions/$(UUID)
UNIT        := oysterd.service
PYTHON      ?= python3
# install-daemon copies the package here and puts an `oysterd` launcher in BINDIR.
PREFIX      ?= $(HOME)/.local
LIBDIR      := $(PREFIX)/lib/oyster
BINDIR      := $(PREFIX)/bin
BLENDER     ?= flatpak run org.blender.Blender
# Linters: pinned versions from make lint-deps. Override to use your own, e.g. make lint RUFF=ruff.
VENV        := $(REPO)/.venv
RUFF        ?= $(VENV)/bin/ruff
MYPY        ?= $(VENV)/bin/mypy
ESLINT      ?= $(REPO)/node_modules/.bin/eslint
PYBUILD     ?= $(VENV)/bin/python -m build
DIST        := $(REPO)/dist

.PHONY: help deps deps-pip lint-deps lint format check test pack dist release dump run fake install install-daemon install-extension \
        uninstall uninstall-daemon uninstall-extension logs shell-logs status devkit headless art spin spin-preview

help:
	@echo "targets: deps deps-pip lint-deps lint format check test dump run fake"
	@echo "         install install-daemon install-extension pack dist release"
	@echo "         uninstall logs shell-logs status devkit headless art spin"

deps:            ## dbus-fast and pytest from the distribution (needs sudo)
	@if command -v zypper >/dev/null; then \
	    py=$$($(PYTHON) -c 'import sys; print(f"python{sys.version_info[0]}{sys.version_info[1]}")'); \
	    sudo zypper in $$py-dbus_fast $$py-pytest; \
	elif command -v dnf >/dev/null; then sudo dnf install python3-dbus-fast python3-pytest; \
	elif command -v apt-get >/dev/null; then sudo apt-get install python3-dbus-fast python3-pytest; \
	elif command -v pacman >/dev/null; then sudo pacman -S --needed python-dbus-fast python-pytest; \
	else echo "unknown package manager: install dbus-fast for $(PYTHON), or run make deps-pip"; exit 1; fi

deps-pip:        ## fallback without sudo: user-site install
	$(PYTHON) -m pip install --user --break-system-packages dbus-fast pytest

lint-deps:       ## pinned ruff and mypy in .venv, eslint in node_modules (no sudo; needs npm)
	$(PYTHON) -m venv --system-site-packages $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	npm ci --no-fund --no-audit

lint:            ## ruff, mypy --strict and eslint; changes nothing
	$(RUFF) check .
	$(RUFF) format --check .
	cd daemon && $(MYPY)
	$(ESLINT) extension
	$(PYTHON) tools/version.py check

format:          ## apply ruff and eslint fixes and formatting
	$(RUFF) check --fix .
	$(RUFF) format .
	$(ESLINT) --fix extension

check: lint test ## what CI runs

test:
	cd daemon && $(PYTHON) -m pytest -q

pack:            ## extension zip for extensions.gnome.org and GitHub releases, in dist/
	mkdir -p $(DIST)
	gnome-extensions pack extension --extra-source=lib --extra-source=assets \
	    --out-dir=$(DIST) --force

dist: pack       ## pack, plus the daemon's sdist and wheel (build comes from make lint-deps)
	$(PYBUILD) daemon --outdir $(DIST)

release:         ## make release VERSION=x.y.z: set the version and date the changelog
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=x.y.z"; exit 1; }
	$(PYTHON) tools/version.py set $(VERSION)
	@echo "Review CHANGELOG.md, then:"
	@echo "  git commit -am 'Oyster $(VERSION)' && git tag -a v$(VERSION) -m 'Oyster $(VERSION)'"
	@echo "  git push origin main v$(VERSION)    # the tag runs .github/workflows/release.yml"

dump:            ## M0 smoke test: print every Apple BLE frame
	cd daemon && $(PYTHON) -m oysterd --dump --any-model --rssi -127

run:             ## run the daemon in the foreground with debug logs
	cd daemon && $(PYTHON) -m oysterd --debug

fake:            ## scripted fake daemon for UI work (stop the real one first)
	python3 daemon/tests/fake_daemon.py

art:
	python3 tools/make_placeholder_art.py

spin:            ## render the AirPods Pro 2 3D turntable (~3 min) and pack it for the extension
	rm -rf render/2420
	$(BLENDER) -b --factory-startup -P $(REPO)/tools/blender/airpods_pro2_spin.py -- --out $(REPO)/render/2420
	python3 tools/pack_spin.py render/2420 extension/assets/2420

spin-preview:    ## render 4 angles only, to render/2420/preview_*.png
	$(BLENDER) -b --factory-startup -P $(REPO)/tools/blender/airpods_pro2_spin.py -- --out $(REPO)/render/2420 --preview 1,25,49,73 --size 384

install: install-daemon install-extension

install-daemon:  ## copy oysterd to $(LIBDIR), add $(BINDIR)/oysterd, install unit + D-Bus activation
	@$(PYTHON) -c 'import dbus_fast' 2>/dev/null || \
	    { echo "dbus-fast is not installed for $(PYTHON): run make deps (or make deps-pip)"; exit 1; }
	rm -rf $(LIBDIR)/oysterd
	mkdir -p $(LIBDIR) $(BINDIR)
	rsync -a --exclude __pycache__ daemon/oysterd $(LIBDIR)/
	printf '%s\n' '#!$(shell command -v $(PYTHON))' \
	    '# Installed by Oyster make install-daemon.' \
	    'import sys' 'sys.path.insert(0, "$(LIBDIR)")' \
	    'from oysterd.__main__ import main' 'sys.exit(main())' > $(BINDIR)/oysterd
	chmod 755 $(BINDIR)/oysterd
	$(BINDIR)/oysterd --install-service

install-extension:
	mkdir -p $(EXT_DIR)
	rsync -a --delete --exclude '*.~*' extension/ $(EXT_DIR)/
	python3 tools/enable_extension.py $(UUID)
	@echo "On Wayland the Shell only loads new extension code after you log out and back in."

uninstall: uninstall-extension uninstall-daemon

uninstall-daemon:
	-$(BINDIR)/oysterd --uninstall-service
	rm -rf $(LIBDIR) $(BINDIR)/oysterd

uninstall-extension:
	-gnome-extensions disable $(UUID)
	rm -rf $(EXT_DIR)

status:
	-systemctl --user --no-pager status $(UNIT)
	-gnome-extensions info $(UUID)
	-busctl --user call io.github.imperriau.Oyster /io/github/imperriau/Oyster io.github.imperriau.Oyster.Status1 GetStatus

logs:
	journalctl --user -u $(UNIT) -f

shell-logs:
	journalctl -f -o cat /usr/bin/gnome-shell

headless:        ## render the extension in an isolated headless Shell and screenshot it
	tools/headless-test.sh

devkit:          ## nested Shell for extension work; needs dbus-run-session (zypper in dbus-1-daemon)
	@command -v dbus-run-session >/dev/null || { echo "dbus-run-session missing: sudo zypper in dbus-1-daemon"; exit 1; }
	G_MESSAGES_DEBUG=all dbus-run-session -- gnome-shell --devkit --wayland
