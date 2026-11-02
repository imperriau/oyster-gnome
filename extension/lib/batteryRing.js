// SPDX-License-Identifier: GPL-3.0-or-later
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';
import Cairo from 'cairo';

const LOW_LEVEL = 0.2;

/**
 * A circular battery gauge. `value` is 0..1 and can be eased like BarLevel's.
 * `known = false` draws a dashed empty track; `charging` draws a bolt and uses the charging colour.
 */
export const BatteryRing = GObject.registerClass({
    GTypeName: 'OysterBatteryRing',
    Properties: {
        'value': GObject.ParamSpec.double(
            'value', null, null, GObject.ParamFlags.READWRITE, 0, 1, 0),
    },
}, class BatteryRing extends St.DrawingArea {
    _init(params = {}) {
        this._value = 0;
        this._known = false;
        this._charging = false;
        super._init({
            style_class: 'airpods-ring',
            y_align: Clutter.ActorAlign.CENTER,
            ...params,
        });
    }

    get value() {
        return this._value;
    }

    set value(v) {
        v = Math.max(0, Math.min(1, v));
        if (v === this._value)
            return;
        this._value = v;
        this.notify('value');
        this.queue_repaint();
    }

    /**
     * @param {number} percent -1 for unknown, else 0..100
     * @param {boolean} charging
     * @param {boolean} animate
     */
    setLevel(percent, charging, animate) {
        const known = percent >= 0;
        const target = known ? percent / 100 : 0;
        const repaint = known !== this._known || charging !== this._charging;
        this._known = known;
        this._charging = charging;
        this.remove_transition('value');
        if (animate && known) {
            this.ease_property('value', target, {
                duration: 400,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        } else {
            this.value = target;
        }
        if (repaint)
            this.queue_repaint();
    }

    _color(node, name) {
        const [found, color] = node.lookup_color(name, false);
        return found ? color : node.get_foreground_color();
    }

    vfunc_repaint() {
        const cr = this.get_context();
        const node = this.get_theme_node();
        const [w, h] = this.get_surface_size();
        const lw = node.get_length('-ring-width') || 4;
        const dash = lw * 0.9;
        const cx = w / 2, cy = h / 2;
        const r = Math.min(w, h) / 2 - lw / 2;

        cr.setLineWidth(lw);
        cr.setLineCap(Cairo.LineCap.ROUND);

        cr.setSourceColor(this._color(node, '-ring-track-color'));
        if (!this._known)
            cr.setDash([dash, dash * 1.3], 0);
        cr.arc(cx, cy, r, 0, 2 * Math.PI);
        cr.stroke();
        cr.setDash([], 0);

        if (this._known && this._value > 0) {
            let colorName = '-ring-color';
            if (this._charging)
                colorName = '-ring-charging-color';
            else if (this._value < LOW_LEVEL)
                colorName = '-ring-low-color';
            cr.setSourceColor(this._color(node, colorName));
            cr.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * this._value);
            cr.stroke();
        }

        if (this._charging) {
            // Small lightning bolt in the centre.
            const s = r * 0.55;
            cr.setSourceColor(this._color(node, '-ring-charging-color'));
            cr.moveTo(cx + 0.15 * s, cy - s);
            cr.lineTo(cx - 0.55 * s, cy + 0.12 * s);
            cr.lineTo(cx - 0.05 * s, cy + 0.12 * s);
            cr.lineTo(cx - 0.15 * s, cy + s);
            cr.lineTo(cx + 0.55 * s, cy - 0.12 * s);
            cr.lineTo(cx + 0.05 * s, cy - 0.12 * s);
            cr.closePath();
            cr.fill();
        }

        cr.$dispose();
    }
});
