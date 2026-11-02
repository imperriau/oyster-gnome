// SPDX-License-Identifier: GPL-3.0-or-later
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {StatusClient} from './lib/dbusClient.js';
import {AirPodsCard} from './lib/card.js';
import {DaemonNotice} from './lib/daemonNotice.js';

export default class OysterExtension extends Extension {
    enable() {
        this._logger = this.getLogger();
        this._card = new AirPodsCard(this);
        this._notice = new DaemonNotice({url: this.metadata.url, logger: this._logger});
        this._client = new StatusClient({
            logger: this._logger,
            onAppeared: () => {
                this._notice?.destroy();
                this._notice = null;
                this._sync();
            },
            onVanished: () => this._card?.hideCard(),
            onChanged: () => this._sync(),
        });
    }

    disable() {
        this._client?.destroy();
        this._client = null;
        this._notice?.destroy();
        this._notice = null;
        this._card?.destroy();
        this._card = null;
        this._logger = null;
    }

    _sync() {
        if (!this._card || !this._client)
            return;
        const s = this._client.status;
        // Preload the model's artwork (incl. the 3D spin sheet) as soon as the AirPods are seen,
        // so it is ready when the lid opens.
        if (s?.Present)
            this._card.setModel(s.Model);
        if (s && s.Present && s.LidOpen)
            this._card.showCard(s);
        else
            this._card.hideCard();
    }
}
