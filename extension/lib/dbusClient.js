// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';

export const BUS_NAME = 'io.github.imperriau.Oyster';
export const OBJECT_PATH = '/io/github/imperriau/Oyster';

const IFACE_XML = `
<node>
  <interface name="io.github.imperriau.Oyster.Status1">
    <property name="Present" type="b" access="read"/>
    <property name="LidOpen" type="b" access="read"/>
    <property name="Model" type="q" access="read"/>
    <property name="ModelName" type="s" access="read"/>
    <property name="Kind" type="s" access="read"/>
    <property name="LeftBattery" type="n" access="read"/>
    <property name="RightBattery" type="n" access="read"/>
    <property name="CaseBattery" type="n" access="read"/>
    <property name="LeftCharging" type="b" access="read"/>
    <property name="RightCharging" type="b" access="read"/>
    <property name="CaseCharging" type="b" access="read"/>
    <property name="LeftInEar" type="b" access="read"/>
    <property name="RightInEar" type="b" access="read"/>
    <property name="Rssi" type="n" access="read"/>
    <property name="Address" type="s" access="read"/>
    <property name="LastSeen" type="t" access="read"/>
    <method name="GetStatus">
      <arg name="status" type="a{sv}" direction="out"/>
    </method>
    <signal name="LidOpened"/>
    <signal name="LidClosed"/>
    <signal name="StatusChanged"/>
  </interface>
</node>`;

const PROPS = [
    'Present', 'LidOpen', 'Model', 'ModelName', 'Kind',
    'LeftBattery', 'RightBattery', 'CaseBattery',
    'LeftCharging', 'RightCharging', 'CaseCharging',
    'LeftInEar', 'RightInEar', 'Rssi', 'Address', 'LastSeen',
];

const StatusProxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);

/**
 * Watches io.github.imperriau.Oyster on the session bus and reports changes.
 * Signals carry no payload; we read the proxy's property cache after each one.
 *
 * The watch asks the bus to start oysterd (D-Bus activation through systemd) if it is not
 * running yet. If it is not installed, the name never appears and DaemonNotice tells the user.
 */
export class StatusClient {
    constructor({logger, onAppeared, onVanished, onChanged}) {
        this._logger = logger;
        this._onAppeared = onAppeared;
        this._onVanished = onVanished;
        this._onChanged = onChanged;
        this._proxy = null;
        this._signalIds = [];
        this._cancellable = new Gio.Cancellable();
        this._watchId = Gio.bus_watch_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameWatcherFlags.AUTO_START,
            () => this._connect(), () => this._disconnect());
    }

    get status() {
        if (!this._proxy)
            return null;
        const s = {};
        for (const p of PROPS)
            s[p] = this._proxy[p];
        return s;
    }

    _connect() {
        if (this._proxy || !this._cancellable)
            return;
        new StatusProxy(Gio.DBus.session, BUS_NAME, OBJECT_PATH, (proxy, error) => {
            if (error) {
                if (!error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                    this._logger?.error(`cannot create proxy: ${error.message}`);
                return;
            }
            if (!this._cancellable)
                return;
            this._proxy = proxy;
            for (const name of ['LidOpened', 'LidClosed', 'StatusChanged'])
                this._signalIds.push(proxy.connectSignal(name, () => this._onChanged()));
            this._logger?.log('connected to oysterd');
            this._onAppeared();
        }, this._cancellable, Gio.DBusProxyFlags.DO_NOT_AUTO_START);
    }

    _disconnect() {
        if (this._proxy) {
            for (const id of this._signalIds)
                this._proxy.disconnectSignal(id);
            this._signalIds = [];
            this._proxy = null;
            this._logger?.log('oysterd vanished');
        }
        this._onVanished();
    }

    destroy() {
        if (this._watchId) {
            Gio.bus_unwatch_name(this._watchId);
            this._watchId = 0;
        }
        this._cancellable?.cancel();
        this._cancellable = null;
        if (this._proxy) {
            for (const id of this._signalIds)
                this._proxy.disconnectSignal(id);
        }
        this._signalIds = [];
        this._proxy = null;
        this._onAppeared = this._onVanished = this._onChanged = () => {};
        this._logger = null;
    }
}
