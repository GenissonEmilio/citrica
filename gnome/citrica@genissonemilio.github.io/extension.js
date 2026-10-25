import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const XML = `<node><interface name="io.github.GenissonEmilio.Citrica.Desktop">
 <method name="Show"><arg type="as" direction="in"/><arg type="s" direction="in"/></method>
 <method name="Hide"/>
 <method name="Status"><arg type="s" direction="out"/></method>
 <method name="ReloadSettings"/>
</interface></node>`;
const R = 132, SIZE = 380;
const DND_SELECTION = Meta.SelectionType.DND ?? Meta.SelectionType.SELECTION_DND ?? 2;

export default class Citrica extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._paths = [];
        this._drag = false;
        this._pending = null;
        this._seq = 0;
        this._read = false;
        this._lastMode = null;
        this._selected = -1;
        this._busy = false;
        this._counts = {opened: 0, dropped: 0, converted: 0, errors: 0};
        this._wheelKeys = new Map();
        this._acceleratorId = global.display.connect('accelerator-activated', (_d, action) => {
            const key = this._wheelKeys.get(action);
            if (!key || !this._wheel) return;
            if (key === 'Escape') this.Hide();
            else if (key === 'Return') {
                if (this._selected >= 0) this._apply(this._items[this._selected]);
            } else {
                const n = this._items?.length ?? 0;
                if (!n) return;
                this._selected = (this._selected + (key === 'Left' ? n - 1 : 1) + n) % n;
                this._buttons.forEach((b, i) => b.set_style(this._buttonStyle(i === this._selected)));
            }
        });
        this._selection = global.display.get_selection();
        this._selectionId = this._selection.connect('owner-changed', (_s, type, owner) => {
            if (type !== DND_SELECTION) return;
            if (owner) this._startDrag();
            else this._endDrag();
        });
        // Global pointer state includes modifiers while a Wayland client owns the drag grab.
        // A timer is used only during a file drag or while the wheel is visible.
        this._keyId = global.stage.connect('captured-event', (_a, event) => {
            if (this._wheel && event.type() === Clutter.EventType.KEY_PRESS) {
                if (event.get_key_symbol() === Clutter.KEY_Escape) {
                    this.Hide();
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this._binding();
        this._settingsId = this._settings.connect('changed', () => this._binding());
        this._indicator = new PanelMenu.Button(0, 'Cítrica');
        this._indicator.add_child(new St.Icon({icon_name: 'view-refresh-symbolic', style_class: 'system-status-icon'}));
        this._indicator.menu.addAction('Mostrar roda · Super+Shift+C', () => this.Show([], 'convert'));
        this._indicator.menu.addAction('Configurações e atalhos', () => this._launch(['--settings']));
        this._indicator.menu.addAction('Sobre o fluxo', () => Main.notify('Cítrica',
            'Arraste um arquivo e pressione Shift. Alt: ferramentas. Ctrl: ações. Solte no setor desejado.'));
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._dbus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._dbus.export(Gio.DBus.session, '/io/github/GenissonEmilio/Citrica/Desktop');
        this._bus = Gio.bus_own_name_on_connection(Gio.DBus.session, 'io.github.GenissonEmilio.Citrica.Desktop',
            Gio.BusNameOwnerFlags.NONE, null, null);
    }

    _binding() {
        Main.wm.removeKeybinding('toggle-wheel');
        Main.wm.addKeybinding('toggle-wheel', this._settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW, () => {
                if (this._wheel) this.Hide(); else this.Show(this._paths, 'convert');
            });
    }

    _command() {
        const file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'citrica', 'desktop.json']));
        try {
            const [ok, data] = file.load_contents(null);
            if (ok) {
                const config = JSON.parse(new TextDecoder().decode(data));
                if (Array.isArray(config.command) && config.command.length && config.command.every(x => typeof x === 'string'))
                    return config.command;
            }
        } catch (_e) { /* An unconfigured install can still use the system launcher. */ }
        return ['citrica'];
    }

    _launch(args) {
        try { return Gio.Subprocess.new([...this._command(), ...args], Gio.SubprocessFlags.NONE); }
        catch (e) { Main.notifyError('Cítrica', e.message); return null; }
    }

    _request(request, callback) {
        try {
            const proc = Gio.Subprocess.new([...this._command(), '--desktop-request', JSON.stringify(request)],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            proc.communicate_utf8_async(null, null, (p, result) => {
                try {
                    const [, stdout, stderr] = p.communicate_utf8_finish(result);
                    if (!p.get_successful()) throw new Error(stderr || stdout || 'Falha no motor local.');
                    callback(JSON.parse(stdout));
                } catch (e) { callback({error: e.message}); }
            });
        } catch (e) { callback({error: e.message}); }
    }

    _startDrag() {
        this._seq++;
        this._drag = true;
        this._read = false;
        this._paths = [];
        this._lastMode = null;
        this._readDrag();
        this._ensurePoll();
    }

    _readDrag() {
        if (this._read) return;
        const mime = this._selection.get_mimetypes(DND_SELECTION) ?? [];
        const type = ['text/uri-list', 'x-special/gnome-icon-list'].find(t => mime.includes(t));
        if (!type) return;
        this._read = true;
        const seq = this._seq;
        const stream = Gio.MemoryOutputStream.new_resizable();
        this._selection.transfer_async(DND_SELECTION, type, 1024 * 1024, stream, null, (s, result) => {
            try {
                s.transfer_finish(result);
                stream.close(null);
                const text = new TextDecoder().decode(stream.steal_as_bytes().get_data());
                if (seq !== this._seq) return;
                this._paths = [...new Set(text.split(/[\r\n]+/).filter(x => x.startsWith('file://'))
                    .map(x => Gio.File.new_for_uri(x).get_path()).filter(Boolean))];
                if (this._paths.length && (this._pending || this._wheel)) {
                    const mode = this._pending || this._mode || 'convert';
                    this._pending = null;
                    this.Show(this._paths, mode);
                }
            } catch (e) { console.warn(`Cítrica: oferta de arraste: ${e.message}`); }
        });
    }

    _ensurePoll() {
        if (this._poll) return;
        this._lastButtons = global.get_pointer()[2];
        this._poll = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            if (!this._drag && !this._wheel) { this._poll = 0; return GLib.SOURCE_REMOVE; }
            const [x, y, mods] = global.get_pointer();
            if (this._drag) {
                this._readDrag();
                const configured = this._settings.get_string('drag-key');
                const trigger = configured === 'super' ?
                    Clutter.ModifierType.SUPER_MASK | Clutter.ModifierType.MOD4_MASK : Clutter.ModifierType.SHIFT_MASK;
                const mode = mods & Clutter.ModifierType.MOD1_MASK ? 'tools' :
                    mods & Clutter.ModifierType.CONTROL_MASK ? 'actions' : mods & trigger ? 'convert' : null;
                if (!mode) this._lastMode = null;
                if (mode && mode !== this._lastMode) {
                    this._lastMode = mode;
                    if (this._paths.length) this.Show(this._paths, mode); else this._pending = mode;
                }
            }
            if (this._wheel) {
                this._highlight(x, y);
                if ((this._lastButtons & Clutter.ModifierType.BUTTON1_MASK) && !(mods & Clutter.ModifierType.BUTTON1_MASK)
                    && this._drag) this._drop();
            }
            this._lastButtons = mods;
            return GLib.SOURCE_CONTINUE;
        });
    }

    _endDrag() {
        // Mutter removes the DND selection as the button is released. Hit testing uses
        // the last pointer location so release is reliable even before the next poll.
        if (this._drag && this._wheel) {
            const [x, y, mods] = global.get_pointer();
            this._highlight(x, y);
            if (!(mods & Clutter.ModifierType.BUTTON1_MASK)) this._drop();
            else this.Hide(); // Escape/source cancellation while the mouse remains held.
        }
        this._drag = false;
        this._pending = null;
        this._seq++;
    }

    Show(paths, mode) {
        if (this._busy) return;
        this._paths = paths;
        this._mode = ['convert', 'tools', 'actions'].includes(mode) ? mode : 'convert';
        this._pending = null;
        if (!this._wheel) {
            const [x, y] = global.get_pointer();
            const monitor = Main.layoutManager.monitors.find(m =>
                x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height)
                ?? Main.layoutManager.primaryMonitor;
            this._origin = [Math.max(monitor.x, Math.min(x - SIZE / 2, monitor.x + monitor.width - SIZE)),
                Math.max(monitor.y + 32, Math.min(y - SIZE / 2, monitor.y + monitor.height - SIZE))];
            this._wheel = new St.Widget({layout_manager: new Clutter.FixedLayout(), width: SIZE, height: SIZE,
                x: this._origin[0], y: this._origin[1], reactive: true, can_focus: true});
            Main.layoutManager.addTopChrome(this._wheel);
            for (const key of ['Escape', 'Left', 'Right', 'Return']) {
                const action = global.display.grab_accelerator(key, Meta.KeyBindingFlags.NONE);
                if (action) {
                    this._wheelKeys.set(action, key);
                    Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.ALL);
                }
            }
            this._counts.opened++;
        }
        this._render([]);
        this._ensurePoll();
        if (!paths.length) return;
        const seq = JSON.stringify([paths, this._mode]);
        this._query = seq;
        this._request({op: 'capabilities', paths, mode: this._mode}, result => {
            if (!this._wheel || this._query !== seq) return;
            if (result.error) { Main.notifyError('Cítrica', result.error); this.Hide(); return; }
            if (!result.items?.length) {
                Main.notify('Cítrica', 'Nenhuma operação disponível para esta seleção. Verifique formatos e dependências.');
                this.Hide();
                return;
            }
            this._render(result.items);
        });
    }

    _render(items, page = 0) {
        this._allItems = items;
        const pages = Math.ceil(items.length / 7);
        const shown = pages > 1 ? [...items.slice(page * 7, page * 7 + 7),
            {id: String((page + 1) % pages), label: `Mais · ${page + 1}/${pages}`, kind: 'page'}] : items;
        this._items = shown;
        this._selected = -1;
        this._buttons = [];
        this._wheel.destroy_all_children();
        const disk = new St.Widget({width: 326, height: 326, x: 27, y: 27,
            style: 'background-color:rgba(25,28,31,0.96);border-radius:163px;border:1px solid rgba(255,255,255,0.18);'});
        this._wheel.add_child(disk);
        const center = new St.Button({width: 100, height: 100, x: 140, y: 140, reactive: true,
            style: 'background-color:#ee753c;border-radius:50px;color:white;font-weight:bold;font-size:14px;'});
        const names = {convert: 'CONVERTER', tools: 'FERRAMENTAS', actions: 'AÇÕES'};
        center.set_child(new St.Label({text: this._paths.length ? `${names[this._mode]}\n${this._paths.length} arquivo(s)` :
            'ARRASTE\nUM ARQUIVO', style: 'text-align:center;font-size:11px;'}));
        center.connect('clicked', () => {
            if (!this._paths.length) this._launch(['--pick']);
            else this.Hide();
        });
        this._wheel.add_child(center);
        for (let i = 0; i < shown.length; i++) {
            const item = shown[i], angle = -Math.PI / 2 + i * 2 * Math.PI / shown.length;
            const button = new St.Button({width: 88, height: 46, can_focus: true, reactive: true,
                x: SIZE / 2 + R * Math.cos(angle) - 44, y: SIZE / 2 + R * Math.sin(angle) - 23,
                style: this._buttonStyle(false)});
            button.set_child(new St.Label({text: item.label, style: 'text-align:center;font-size:11px;'}));
            button.connect('clicked', () => this._apply(item));
            this._wheel.add_child(button);
            this._buttons.push(button);
        }
        const hint = new St.Label({text: this._paths.length && !items.length ? 'Carregando…' :
            'Shift: converter  ·  Alt: ferramentas  ·  Ctrl: ações',
        style: 'color:#eee;font-size:10px;background-color:rgba(25,28,31,0.95);border-radius:10px;padding:7px;'});
        hint.set_position(25, SIZE - 5);
        this._wheel.add_child(hint);
        if (!items.length && this._paths.length) this._wheel.opacity = 0;
        else this._wheel.opacity = 255;
        if ((items.length || !this._paths.length) && this._settings.get_boolean('animations')) {
            this._wheel.set_pivot_point(0.5, 0.5);
            this._wheel.scale_x = this._wheel.scale_y = 0.7;
            this._wheel.opacity = 0;
            this._wheel.ease({scale_x: 1, scale_y: 1, opacity: 255, duration: 180,
                mode: Clutter.AnimationMode.EASE_OUT_BACK});
        }
    }

    _buttonStyle(active) {
        return `background-color:${active ? '#ee753c' : '#363c40'};color:white;border-radius:23px;` +
            `border:1px solid ${active ? '#ffc198' : '#555b60'};padding:3px;`;
    }

    _highlight(x, y) {
        if (!this._wheel || !this._items?.length) return;
        const dx = x - this._origin[0] - SIZE / 2, dy = y - this._origin[1] - SIZE / 2;
        const radius = Math.hypot(dx, dy), n = Math.min(10, this._items.length);
        const angle = (Math.atan2(dy, dx) + Math.PI / 2 + 2 * Math.PI) % (2 * Math.PI);
        const selected = radius > 76 && radius < 190 ? Math.round(angle / (2 * Math.PI) * n) % n : -1;
        if (selected === this._selected) return;
        this._selected = selected;
        this._buttons.forEach((b, i) => b.set_style(this._buttonStyle(i === selected)));
    }

    _drop() {
        if (this._busy || !this._wheel) return;
        const item = this._items?.[this._selected];
        this._counts.dropped++;
        if (item) this._apply(item); else this.Hide();
    }

    _apply(item) {
        if (item.kind === 'page') {
            this._render(this._allItems, Number(item.id));
            return;
        }
        const paths = [...this._paths];
        this.Hide();
        if (!paths.length) return;
        if (item.kind === 'tool' && item.id === 'copy_path') {
            St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, paths.join('\n'));
            Main.notify('Cítrica', 'Caminhos copiados.');
            return;
        }
        if (item.kind === 'tool') {
            this._launch(['--tool', item.id, ...paths]);
            return;
        }
        this._busy = true;
        Main.notify('Cítrica', `Convertendo ${paths.length} arquivo(s) para ${item.label}…`);
        this._request({op: 'convert', paths, format: item.id}, result => {
            this._busy = false;
            if (result.error || result.errors?.length) {
                this._counts.errors++;
                Main.notifyError('Cítrica', result.error || result.errors.join('\n'));
            } else {
                this._counts.converted += result.outputs?.length ?? 0;
                Main.notify('Cítrica · concluído', `${result.outputs.length} arquivo(s) salvo(s) junto ao original.`);
            }
        });
    }

    Hide() {
        this._query = null;
        for (const action of this._wheelKeys.keys()) global.display.ungrab_accelerator(action);
        this._wheelKeys.clear();
        this._wheel?.destroy();
        this._wheel = null;
        this._selected = -1;
    }

    Status() {
        return JSON.stringify({version: 2, revision: 3, visible: !!this._wheel, dragging: this._drag,
            animation: this._wheel ? {opacity: this._wheel.opacity, scale: this._wheel.scale_x} : null,
            paths: this._paths, mode: this._mode, origin: this._origin, selected: this._selected,
            items: this._items, busy: this._busy, counts: this._counts,
            shortcut: this._settings.get_strv('toggle-wheel'), dragKey: this._settings.get_string('drag-key')});
    }

    ReloadSettings() { this._binding(); }

    disable() {
        this.Hide();
        if (this._poll) GLib.source_remove(this._poll);
        this._poll = 0;
        global.stage.disconnect(this._keyId);
        global.display.disconnect(this._acceleratorId);
        this._selection.disconnect(this._selectionId);
        this._settings.disconnect(this._settingsId);
        Main.wm.removeKeybinding('toggle-wheel');
        this._indicator.destroy();
        this._dbus.unexport();
        Gio.bus_unown_name(this._bus);
    }
}
