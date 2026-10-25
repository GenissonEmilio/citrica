// Test-only extension. This directory is never installed or included in releases.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML = `<node><interface name="io.github.GenissonEmilio.Citrica.Test">
 <method name="Pointer"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="Button"><arg type="b" direction="in"/></method>
 <method name="Key"><arg type="u" direction="in"/><arg type="b" direction="in"/></method>
 <method name="Screenshot"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
 <method name="Windows"><arg type="s" direction="out"/></method>
 <method name="State"><arg type="s" direction="out"/></method>
 <method name="Clipboard"><arg type="s" direction="out"/></method>
 <method name="Prepare"/>
 <method name="PlaceWindow"><arg type="s" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="Quit"/>
</interface></node>`;
export default class Harness extends Extension {
    enable() {
        const seat = Clutter.get_default_backend().get_default_seat();
        this.pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this.keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.dbus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this.dbus.export(Gio.DBus.session, '/io/github/GenissonEmilio/Citrica/Test');
        this.bus = Gio.bus_own_name_on_connection(Gio.DBus.session, 'io.github.GenissonEmilio.Citrica.Test', 0, null, null);
        Main.overview.hide();
    }
    Pointer(x, y) { this.pointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y); }
    Button(pressed) { this.pointer.notify_button(GLib.get_monotonic_time(), 1,
        pressed ? Clutter.ButtonState.PRESSED : Clutter.ButtonState.RELEASED); }
    Key(key, pressed) { this.keyboard.notify_keyval(GLib.get_monotonic_time(), key,
        pressed ? Clutter.KeyState.PRESSED : Clutter.KeyState.RELEASED); }
    Windows() { return JSON.stringify(global.get_window_actors().map(a => {
        const r = a.meta_window.get_frame_rect();
        return {id:a.meta_window.get_stable_sequence(),title:a.meta_window.title,rect:[r.x,r.y,r.width,r.height],visible:a.visible,
            minimized:a.meta_window.minimized,workspace:a.meta_window.get_workspace().index()};
    })); }
    Prepare() { Main.welcomeDialog?.close(); Main.overview.hide(); }
    State() { return JSON.stringify({pointer:global.get_pointer(),
        focus:global.display.focus_window?.get_stable_sequence(),overview:Main.overview.visible}); }
    ClipboardAsync(_args, invocation) {
        St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD, (_c, text) =>
            invocation.return_value(new GLib.Variant('(s)', [text ?? ''])));
    }
    PlaceWindow(title, x, y) {
        const w = global.get_window_actors().map(a => a.meta_window).find(w =>
            title === `window-id:${w.get_stable_sequence()}` || w.title === title);
        if (w) {
            Main.welcomeDialog?.close(); Main.overview.hide();
            w.unminimize(); w.change_workspace(global.workspace_manager.get_active_workspace());
            w.move_frame(false, x, y); Main.activateWindow(w);
        }
    }
    ScreenshotAsync([path], invocation) {
        const out = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        const shot = new Shell.Screenshot();
        shot.screenshot(false, out, (s, result) => {
            try { s.screenshot_finish(result); out.close(null); invocation.return_value(new GLib.Variant('(b)', [true])); }
            catch (e) { invocation.return_dbus_error('io.github.GenissonEmilio.Citrica.Test.Error', e.message); }
        });
    }
    Quit() { GLib.idle_add(GLib.PRIORITY_DEFAULT, () => { global.context.terminate(); return GLib.SOURCE_REMOVE; }); }
    disable() { this.dbus.unexport(); Gio.bus_unown_name(this.bus); this.pointer = this.keyboard = null; }
}
