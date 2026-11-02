// SPDX-License-Identifier: GPL-3.0-or-later
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Layout from 'resource:///org/gnome/shell/ui/layout.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {BatteryRing} from './batteryRing.js';
import {loadArtwork} from './artwork.js';
import {SpinView, loadSheet} from './spinView.js';

const SHOW_TIME = 300;
const HIDE_TIME = 220;
const SLIDE_DISTANCE = 60;
const HERO_SIZE = 150;
const CASE_SIZE = 120;
const POD_SIZE = 64;

/**
 * Bottom-centre overlay, modelled on js/ui/osdWindow.js.
 *
 * The outer actor is tracked as chrome with trackFullscreen, which means the layout manager
 * owns its `visible` flag. All showing/hiding/animation therefore happens on the inner box.
 */
export const AirPodsCard = GObject.registerClass({
    GTypeName: 'OysterCard',
}, class AirPodsCard extends Clutter.Actor {
    _init(extension) {
        super._init({
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.END,
            reactive: false,
        });
        this._extension = extension;
        this._logger = extension.getLogger();
        this._shown = false;
        this._unredirectDisabled = false;
        this._modelId = null;
        this._single = false;
        this._hero = null;
        this._artCancellable = null;

        this.add_constraint(new Layout.MonitorConstraint({primary: true}));

        this._box = new St.BoxLayout({
            style_class: 'airpods-card',
            orientation: Clutter.Orientation.HORIZONTAL,
            visible: false,
            opacity: 0,
        });
        this.add_child(this._box);

        // Artwork: left pod, right pod, case.
        this._art = new St.BoxLayout({
            style_class: 'airpods-card-art',
            orientation: Clutter.Orientation.HORIZONTAL,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._box.add_child(this._art);
        this._icons = {
            left: new St.Icon({icon_size: POD_SIZE, y_align: Clutter.ActorAlign.CENTER}),
            right: new St.Icon({icon_size: POD_SIZE, y_align: Clutter.ActorAlign.CENTER}),
            case: new St.Icon({icon_size: CASE_SIZE, y_align: Clutter.ActorAlign.CENTER}),
        };
        this._art.add_child(this._icons.left);
        this._art.add_child(this._icons.right);
        this._art.add_child(this._icons.case);

        // Info column: title + three rows.
        const info = new St.BoxLayout({
            style_class: 'airpods-card-info',
            orientation: Clutter.Orientation.VERTICAL,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._box.add_child(info);
        this._title = new St.Label({style_class: 'airpods-card-title'});
        info.add_child(this._title);

        this._rows = {};
        for (const [key, label] of [['left', 'Left'], ['right', 'Right'], ['case', 'Case']]) {
            const row = new St.BoxLayout({
                style_class: 'airpods-card-row',
                orientation: Clutter.Orientation.HORIZONTAL,
            });
            const ring = new BatteryRing();
            const name = new St.Label({
                text: label,
                style_class: 'airpods-card-label',
                y_align: Clutter.ActorAlign.CENTER,
            });
            const pct = new St.Label({
                style_class: 'airpods-card-percent',
                x_expand: true,
                x_align: Clutter.ActorAlign.END,
                y_align: Clutter.ActorAlign.CENTER,
            });
            row.add_child(ring);
            row.add_child(name);
            row.add_child(pct);
            info.add_child(row);
            this._rows[key] = {row, ring, name, pct, label};
        }

        // Cleanup runs on destroy no matter who destroys us (disable() or Shell teardown).
        this.connect('destroy', () => this._onDestroy());
        Main.layoutManager.addTopChrome(this, {trackFullscreen: true});
    }

    showCard(status) {
        if (!this._box)
            return;
        this._update(status, this._shown);
        if (this._shown)
            return;
        this._shown = true;

        if (!this._unredirectDisabled) {
            global.compositor.disable_unredirect();
            this._unredirectDisabled = true;
        }
        this.get_parent()?.set_child_above_sibling(this, null);

        const box = this._box;
        box.remove_all_transitions();
        if (!box.visible) {
            box.opacity = 0;
            box.translation_y = SLIDE_DISTANCE;
            box.show();
        }
        box.ease({
            opacity: 255,
            translation_y: 0,
            duration: SHOW_TIME,
            mode: Clutter.AnimationMode.EASE_OUT_BACK,
        });
        this._hero?.play();
    }

    hideCard() {
        if (!this._box || !this._shown)
            return;
        this._shown = false;

        const box = this._box;
        box.remove_all_transitions();
        box.ease({
            opacity: 0,
            translation_y: SLIDE_DISTANCE,
            duration: HIDE_TIME,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onStopped: isFinished => {
                if (!isFinished || this._shown || !this._box)
                    return;
                box.hide();
                this._hero?.stop();
                this._restoreUnredirect();
            },
        });
    }

    _restoreUnredirect() {
        if (this._unredirectDisabled) {
            global.compositor.enable_unredirect();
            this._unredirectDisabled = false;
        }
    }

    _update(s, animate) {
        if (s.Model !== this._modelId)
            this.setModel(s.Model);

        const single = this._single = s.Kind === 'single';
        this._title.text = s.ModelName || 'AirPods';
        this._syncIcons();
        this._rows.right.row.visible = !single;
        this._rows.left.name.text = single ? 'Battery' : this._rows.left.label;
        this._rows.case.row.visible = !single;

        this._setRow('left', s.LeftBattery, s.LeftCharging, animate);
        this._setRow('right', s.RightBattery, s.RightCharging, animate);
        this._setRow('case', s.CaseBattery, s.CaseCharging, animate);
    }

    _setRow(key, level, charging, animate) {
        const r = this._rows[key];
        r.ring.setLevel(level, charging, animate);
        r.pct.text = level >= 0 ? `${level} %` : '–';
    }

    /**
     * Switch artwork to a model: static parts once their files are found, then the 3D spin once
     * its sheet has been decoded. All file access is async. Safe to call repeatedly; does nothing
     * if unchanged. A newer call cancels the loads of an older one.
     */
    setModel(modelId) {
        if (!this._box || modelId === this._modelId)
            return;
        this._modelId = modelId;
        this._clearArt();
        const cancellable = this._artCancellable = new Gio.Cancellable();
        this._loadArt(modelId, cancellable).catch(e => {
            if (!e.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                this._logger.warn(`cannot load artwork for model 0x${modelId.toString(16)}: ${e.message}`);
        });
    }

    async _loadArt(modelId, cancellable) {
        const {icons, hero} = await loadArtwork(this._extension, modelId, cancellable, this._logger);
        if (cancellable.is_cancelled() || !this._box)
            return;
        for (const [part, gicon] of Object.entries(icons))
            this._icons[part].gicon = gicon;
        if (!hero)
            return;

        const pixbuf = await loadSheet(hero.file, cancellable);
        if (cancellable.is_cancelled() || !this._box)
            return;
        this._hero = new SpinView(pixbuf, hero.meta, HERO_SIZE);
        this._art.add_child(this._hero);
        this._syncIcons();
        if (this._shown)
            this._hero.play();
    }

    _clearArt() {
        this._artCancellable?.cancel();
        this._artCancellable = null;
        this._hero?.destroy();
        this._hero = null;
        for (const icon of Object.values(this._icons))
            icon.gicon = null;
        this._syncIcons();
    }

    /** Static parts show only without a spin; a single-battery model has no right pod and no case. */
    _syncIcons() {
        this._icons.left.visible = !this._hero;
        this._icons.case.visible = !this._hero && !this._single;
        this._icons.right.visible = !this._hero && !this._single;
    }

    _onDestroy() {
        // The layout manager untracks chrome on 'destroy' itself; no removeChrome() needed.
        this._artCancellable?.cancel();
        this._artCancellable = null;
        this._hero = null; // destroyed with us as a descendant
        this._restoreUnredirect();
        this._box = null;
        this._extension = null;
        this._logger = null;
        this._icons = null;
        this._rows = null;
    }
});
