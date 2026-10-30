import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {WheelView, SIZE, pickSector} from './wheel.js';

const XML = `<node><interface name="io.github.GenissonEmilio.Citrica.Desktop">
 <method name="Show"><arg type="as" direction="in"/><arg type="s" direction="in"/></method>
 <method name="Hide"/>
 <method name="Status"><arg type="s" direction="out"/></method>
 <method name="ReloadSettings"/>
</interface></node>`;
const DND_SELECTION = Meta.SelectionType.DND ?? Meta.SelectionType.SELECTION_DND ?? 2;

export default class Citrica extends Extension {
    enable() {
        this._enabled = true;
        this._settings = this.getSettings();
        this._paths = [];
        this._items = [];
        this._mode = 'convert';
        this._viewToken = 0;
        this._closingViews = new Set();
        this._drag = false;
        this._pending = null;
        this._seq = 0;
        this._read = false;
        this._lastMode = null;
        this._dropHandled = false;
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
                this._keyboardPointer = global.get_pointer().slice(0, 2);
                this._selected = this._selected < 0 ? (key === 'Left' ? n - 1 : 0) :
                    (this._selected + (key === 'Left' ? n - 1 : 1)) % n;
                this._view.select(this._selected);
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
        this._settingsId = this._settings.connect('changed', (_settings, key) => {
            if (key === 'wheel-theme') this._view?.setTheme(this._settings.get_string('wheel-theme'));
            else if (key === 'toggle-wheel') this._binding();
        });
        this._indicator = new PanelMenu.Button(0, 'Cítrica');
        this._indicator.add_child(new St.Icon({icon_name: 'view-refresh-symbolic', style_class: 'system-status-icon'}));
        this._indicator.menu.addAction('Mostrar roda', () => this.Show([], 'convert'));
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
                const liveDrag = this._drag && (global.get_pointer()[2] & Clutter.ModifierType.BUTTON1_MASK);
                if (this._wheel) this.Hide(); else this.Show(liveDrag ? this._paths : [], 'convert');
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
                    if (!this._enabled) return;
                    if (!p.get_successful()) throw new Error(stderr || stdout || 'Falha no motor local.');
                    callback(JSON.parse(stdout));
                } catch (e) { callback({error: e.message}); }
            });
        } catch (e) { callback({error: e.message}); }
    }

    _startDrag() {
        if (!(global.get_pointer()[2] & Clutter.ModifierType.BUTTON1_MASK)) return;
        this._seq++;
        this._viewToken++;
        this._drag = true;
        this._read = false;
        this._paths = [];
        this._lastMode = null;
        this._dropHandled = false;
        this._selectionInfo = null;
        this._palette = null;
        this._palettePending = null;
        this._view?.setInfo(null, true);
        if (this._wheel) this._render([], 0, true);
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
                if (seq !== this._seq || !this._drag ||
                    !(global.get_pointer()[2] & Clutter.ModifierType.BUTTON1_MASK)) return;
                this._paths = [...new Set(text.split(/[\r\n]+/).filter(x => x.startsWith('file://'))
                    .map(x => Gio.File.new_for_uri(x).get_path()).filter(Boolean))];
                if (this._paths.length) this._prefetch();
                if (this._paths.length && (this._pending || this._wheel)) {
                    const mode = this._pending || this._mode || 'convert';
                    this._pending = null;
                    this.Show(this._paths, mode);
                }
            } catch (e) { console.warn(`Cítrica: oferta de arraste: ${e.message}`); }
        });
    }

    _prefetch() {
        const serial = this._seq, paths = [...this._paths], key = JSON.stringify(paths);
        this._palettePending = key;
        this._request({op: 'palette', paths}, result => {
            if (serial !== this._seq || !this._drag || JSON.stringify(this._paths) !== key) return;
            this._palettePending = null;
            if (result.error) {
                if (this._wheel && JSON.stringify(this._paths) === key) {
                    Main.notifyError('Cítrica', result.error);
                    this.Hide();
                }
                return;
            }
            this._palette = {key, ...result};
            if (this._wheel && JSON.stringify(this._paths) === key) this._showPalette(result);
        });
    }

    _showPalette(result) {
        const items = result.modes ? result.modes[this._mode] : result.items;
        if (!items?.length) {
            Main.notify('Cítrica', 'Nenhuma operação disponível para esta seleção. Verifique formatos e dependências.');
            this.Hide();
            return;
        }
        this._selectionInfo = result.selection;
        this._view.setInfo(result.selection);
        this._render(items);
    }

    _ensurePoll() {
        if (this._poll) return;
        this._lastButtons = global.get_pointer()[2];
        this._poll = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            if (!this._drag && !this._wheel) { this._poll = 0; return GLib.SOURCE_REMOVE; }
            const [x, y, mods] = global.get_pointer();
            if (this._drag && !(mods & Clutter.ModifierType.BUTTON1_MASK)) this._endDrag();
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
        this._lastMode = null;
        if (!this._wheel) this._paths = [];
        this._seq++;
    }

    Show(paths, mode) {
        if (this._busy) return;
        const samePaths = JSON.stringify(paths) === JSON.stringify(this._paths);
        this._paths = [...paths];
        if (!samePaths) {
            this._selectionInfo = null;
            this._palette = null;
            this._palettePending = null;
        }
        const token = ++this._viewToken;
        this._mode = ['convert', 'tools', 'actions'].includes(mode) ? mode : 'convert';
        this._pending = null;
        if (!this._wheel) {
            this._destroyClosing();
            const [x, y] = global.get_pointer();
            const monitor = Main.layoutManager.monitors.find(m =>
                x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height)
                ?? Main.layoutManager.primaryMonitor;
            this._origin = [Math.max(monitor.x, Math.min(x - SIZE / 2, monitor.x + monitor.width - SIZE)),
                Math.max(monitor.y + 32, Math.min(y - SIZE / 2, monitor.y + monitor.height - SIZE - 24))];
            this._view = new WheelView({animations: () => this._settings.get_boolean('animations'),
                theme: this._settings.get_string('wheel-theme'),
                activate: (px, py) => {
                    if (this._drag) return;
                    this._highlight(px, py);
                    const item = this._items[this._selected];
                    if (item) this._apply(item);
                },
                pick: () => {
                    const empty = !this._paths.length;
                    this.Hide();
                    if (empty) this._launch(['--pick']);
                }});
            this._wheel = this._view.actor;
            this._wheel.set_position(...this._origin);
            Main.layoutManager.addTopChrome(this._wheel);
            // Keep the compositor's native drag thumbnail above the sectors.
            // Lower only our actor; leave Shell's feedback layer untouched.
            const parent = this._wheel.get_parent();
            const feedback = global.compositor.get_feedback_group();
            if (feedback.get_parent() === parent)
                parent.set_child_below_sibling(this._wheel, feedback);
            for (const key of ['Escape', 'Left', 'Right', 'Return']) {
                const action = global.display.grab_accelerator(key, Meta.KeyBindingFlags.NONE);
                if (action) {
                    this._wheelKeys.set(action, key);
                    Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.ALL);
                }
            }
            this._counts.opened++;
            this._view.open();
        }
        this._view.setInfo(this._selectionInfo || (paths.length ? {count: paths.length, icon: 'text-x-generic'} : null),
            paths.length > 0 && !this._selectionInfo);
        this._render([], 0, paths.length > 0);
        this._ensurePoll();
        if (!paths.length) return;
        const key = JSON.stringify(paths);
        if (this._palette?.key === key) { this._showPalette(this._palette); return; }
        if (this._palettePending === key) return;
        this._request({op: 'capabilities', paths, mode: this._mode}, result => {
            if (!this._wheel || this._viewToken !== token) return;
            if (result.error) { Main.notifyError('Cítrica', result.error); this.Hide(); return; }
            this._showPalette(result);
        });
    }

    _render(items, page = 0, loading = false) {
        this._allItems = items;
        const pages = Math.ceil(items.length / 7);
        this._items = pages > 1 ? [...items.slice(page * 7, page * 7 + 7),
            {id: String((page + 1) % pages), label: `Mais · ${page + 1}/${pages}`, kind: 'page'}] : items;
        this._selected = -1;
        this._keyboardPointer = null;
        this._view.render(this._items, {hasFiles: !!this._paths.length, loading});
    }

    _highlight(x, y) {
        if (!this._wheel || !this._items?.length) return;
        if (this._keyboardPointer?.[0] === x && this._keyboardPointer?.[1] === y) return;
        this._keyboardPointer = null;
        const selected = pickSector(x - this._origin[0], y - this._origin[1], this._items.length);
        if (selected === this._selected) return;
        this._selected = selected;
        this._view.select(selected);
    }

    _drop() {
        if (this._busy || !this._wheel || this._dropHandled) return;
        this._dropHandled = true;
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
        if (item.kind === 'tool' && item.id === 'copy') {
            const uris = paths.map(p => Gio.File.new_for_path(p).get_uri());
            const bytes = new GLib.Bytes(new TextEncoder().encode('copy\n' + uris.join('\n')));
            St.Clipboard.get_default().set_content(St.ClipboardType.CLIPBOARD, 'x-special/gnome-copied-files', bytes);
            Main.notify('Cítrica', 'Arquivos copiados. Cole na pasta de destino.');
            return;
        }
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
        // Reset synchronously before the closing animation or any subprocess
        // finishes. A new opening never inherits a previous file or reply.
        this._viewToken++;
        this._seq++;
        this._paths = [];
        this._items = [];
        this._allItems = [];
        this._selectionInfo = null;
        this._palette = null;
        this._palettePending = null;
        this._pending = null;
        this._drag = false;
        this._lastMode = null;
        this._keyboardPointer = null;
        this._dropHandled = true;
        this._selected = -1;
        for (const action of this._wheelKeys.keys()) global.display.ungrab_accelerator(action);
        this._wheelKeys.clear();
        const view = this._view;
        this._view = null;
        this._wheel = null;
        if (view) {
            this._closingViews.add(view);
            view.close(() => {
                if (this._closingViews.delete(view)) view.destroy();
            });
        }
    }

    _destroyClosing() {
        for (const view of this._closingViews) view.destroy();
        this._closingViews.clear();
    }

    Status() {
        return JSON.stringify({version: 3, revision: 4, appearance: 'annular-sectors',
            visible: !!this._wheel, dragging: this._drag, closing: this._closingViews.size,
            animation: this._wheel ? {opacity: this._wheel.opacity, scale: this._wheel.scale_x} : null,
            motion: this._view?.motionState() ?? null, cachedSelection: !!this._palette,
            paths: this._paths, mode: this._mode, origin: this._origin, selected: this._selected,
            items: this._items, selection: this._selectionInfo, busy: this._busy, counts: this._counts,
            shortcut: this._settings.get_strv('toggle-wheel'), dragKey: this._settings.get_string('drag-key'),
            wheelTheme: this._settings.get_string('wheel-theme')});
    }

    ReloadSettings() {
        this._binding();
        this._view?.setTheme(this._settings.get_string('wheel-theme'));
    }

    disable() {
        this._enabled = false;
        this.Hide();
        this._destroyClosing();
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
