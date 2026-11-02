// SPDX-License-Identifier: GPL-3.0-or-later
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import GObject from 'gi://GObject';
import St from 'gi://St';

/**
 * Plays a pre-rendered turntable from one sprite sheet.
 *
 * The sheet is uploaded once as a single texture on a child actor that is larger than this
 * clipped widget; each frame just translates the child. Frames advance on the stage's frame
 * clock through a Clutter.Timeline, so the animation pauses by itself when not painted.
 */
export const SpinView = GObject.registerClass({
    GTypeName: 'OysterSpinView',
}, class SpinView extends St.Widget {
    /**
     * @param {GdkPixbuf.Pixbuf} pixbuf the whole sheet
     * @param {object} meta hero.json contents
     * @param {number} size logical size of one frame on screen
     */
    _init(pixbuf, meta, size) {
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const px = size * scale;
        super._init({
            width: px,
            height: px,
            clip_to_allocation: true,
            layout_manager: new Clutter.FixedLayout(),
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._meta = meta;
        this._px = px;
        this._frame = -1;

        const content = St.ImageContent.new_with_preferred_size(pixbuf.width, pixbuf.height);
        const cogl = global.stage.context.get_backend().get_cogl_context();
        content.set_bytes(cogl, pixbuf.read_pixel_bytes(),
            pixbuf.has_alpha ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
            pixbuf.width, pixbuf.height, pixbuf.rowstride);

        this._sheet = new Clutter.Actor({
            content,
            width: meta.columns * px,
            height: meta.rows * px,
        });
        this._sheet.set_content_scaling_filters(
            Clutter.ScalingFilter.TRILINEAR, Clutter.ScalingFilter.LINEAR);
        this.add_child(this._sheet);

        const loopMs = Math.round(meta.frames / meta.fps * 1000);
        this._timeline = new Clutter.Timeline({actor: this, duration: loopMs, repeat_count: -1});
        this._timeline.connect('new-frame', (_t, msecs) =>
            this._setFrame(Math.floor(msecs / 1000 * meta.fps) % meta.frames));
        this.connect('destroy', () => {
            this._timeline?.stop();
            this._timeline = null;
        });
        this._setFrame(0);
    }

    _setFrame(i) {
        if (i === this._frame)
            return;
        this._frame = i;
        const {columns} = this._meta;
        this._sheet.translation_x = -(i % columns) * this._px;
        this._sheet.translation_y = -Math.floor(i / columns) * this._px;
    }

    play() {
        // Respect "Reduce animation" / disabled animations: show the first frame only.
        if (!St.Settings.get().enable_animations) {
            this._setFrame(0);
            return;
        }
        this._timeline?.start();
    }

    stop() {
        this._timeline?.stop();
    }
});

/**
 * Decode a sheet off the main loop.
 *
 * @param {import('gi://Gio').File} file
 * @param {import('gi://Gio').Cancellable} cancellable
 * @returns {Promise<GdkPixbuf.Pixbuf>}
 */
export function loadSheet(file, cancellable) {
    return new Promise((resolve, reject) => {
        file.read_async(0, cancellable, (f, res) => {
            let stream;
            try {
                stream = f.read_finish(res);
            } catch (e) {
                reject(e);
                return;
            }
            GdkPixbuf.Pixbuf.new_from_stream_async(stream, cancellable, (_s, res2) => {
                try {
                    resolve(GdkPixbuf.Pixbuf.new_from_stream_finish(res2));
                } catch (e) {
                    reject(e);
                } finally {
                    stream.close_async(0, null, null);
                }
            });
        });
    });
}
