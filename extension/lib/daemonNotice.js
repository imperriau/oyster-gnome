// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';

import {BUS_NAME} from './dbusClient.js';

/** How long oysterd may take to appear on the bus before the user is told. */
const GRACE_SECONDS = 10;

// At most one notice per Shell session: the Shell disables and re-enables extensions around every
// screen lock, and the notice should not come back after each unlock.
let shownThisSession = false;

/** @returns {Promise<boolean>} whether the session bus can start oysterd (it is installed) */
function isActivatable(cancellable) {
    return new Promise((resolve, reject) => {
        Gio.DBus.session.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'ListActivatableNames', null, new GLib.VariantType('(as)'),
            Gio.DBusCallFlags.NONE, -1, cancellable, (conn, res) => {
                try {
                    const [names] = conn.call_finish(res).deepUnpack();
                    resolve(names.includes(BUS_NAME));
                } catch (e) {
                    reject(e);
                }
            });
    });
}

/**
 * Tells the user once when the card cannot work because oysterd is missing or does not start.
 * extensions.gnome.org cannot ship the daemon, so this is the first thing many users need.
 *
 * The extension destroys the notice as soon as oysterd appears; if that happens within the grace
 * period, nothing is shown.
 */
export class DaemonNotice {
    /**
     * @param {object} params
     * @param {string} params.url the project page; the notice links to its README sections
     * @param {object} params.logger the extension's logger
     */
    constructor({url, logger}) {
        this._url = url;
        this._logger = logger;
        this._source = null;
        this._cancellable = new Gio.Cancellable();
        this._timeoutId = 0;
        if (!shownThisSession) {
            this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, GRACE_SECONDS, () => {
                this._timeoutId = 0;
                this._check().catch(e => {
                    if (!e.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                        this._logger?.error(`cannot check for oysterd: ${e.message}`);
                });
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    async _check() {
        const installed = await isActivatable(this._cancellable);
        if (!this._cancellable || shownThisSession)
            return;
        if (installed) {
            this._notify('Oyster: the oysterd daemon did not start',
                'Run “journalctl --user -u oysterd” to see why.',
                'Help', `${this._url}#if-the-card-never-appears`);
        } else {
            this._notify('Oyster needs the oysterd daemon',
                'Install it to see your AirPods battery card.',
                'Install instructions', `${this._url}#install`);
        }
    }

    _notify(title, body, actionLabel, url) {
        shownThisSession = true;
        this._logger?.warn(title);
        this._source = new MessageTray.Source({title: 'Oyster', iconName: 'audio-headphones-symbolic'});
        // The source destroys itself when its notification is dismissed.
        this._source.connect('destroy', () => (this._source = null));
        Main.messageTray.add(this._source);

        const notification = new MessageTray.Notification({source: this._source, title, body});
        const open = () => Gio.app_info_launch_default_for_uri(url, global.create_app_launch_context(0, -1));
        notification.connect('activated', open);
        notification.addAction(actionLabel, open);
        this._source.addNotification(notification);
    }

    destroy() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        this._cancellable?.cancel();
        this._cancellable = null;
        this._source?.destroy();
        this._source = null;
        this._logger = null;
    }
}
