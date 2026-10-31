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
 <method name="CloseWindow"><arg type="u" direction="in"/><arg type="u" direction="in"/></method>
 <method name="State"><arg type="s" direction="out"/></method>
 <method name="DragLayers"><arg type="s" direction="out"/></method>
 <method name="Clipboard"><arg type="s" direction="out"/></method>
 <method name="ObserveMotion"/>
 <method name="Motion"><arg type="s" direction="out"/></method>
 <method name="StartRecording"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
 <method name="StopRecording"><arg type="b" direction="out"/></method>
 <method name="Prepare"/>
 <method name="PlaceWindow"><arg type="s" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="Quit"/>
</interface></node>`;
export default class Harness extends Extension {
    enable() {
        const backend = Clutter.get_default_backend?.() ?? global.stage.context.get_backend();
        const seat = backend.get_default_seat();
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
        return {id:a.meta_window.get_stable_sequence(),pid:a.meta_window.get_pid(),title:a.meta_window.title,rect:[r.x,r.y,r.width,r.height],visible:a.visible,
            minimized:a.meta_window.minimized,workspace:a.meta_window.get_workspace().index()};
    })); }
    CloseWindow(pid, id) {
        // Target only the exact test-owned Wayland client. This is the native
        // window-manager close request, independent of keyboard focus.
        const window = global.get_window_actors().map(actor => actor.meta_window).find(w =>
            w.get_pid() === pid && w.get_stable_sequence() === id);
        if (!window) throw new Error('The specified test window is no longer present');
        window.delete(global.get_current_time());
    }
    Prepare() { Main.welcomeDialog?.close(); Main.overview.hide(); }
    State() { return JSON.stringify({pointer:global.get_pointer(),
        focus:global.display.focus_window?.get_stable_sequence(),overview:Main.overview.visible,
        systemAnimations: St.Settings.get().enable_animations}); }
    DragLayers() {
        const feedback = global.compositor.get_feedback_group();
        const extension = Main.extensionManager.lookup('citrica@genissonemilio.github.io')?.stateObj;
        const wheel = extension?._wheel;
        const parent = feedback.get_parent();
        const siblings = parent.get_children();
        return JSON.stringify({feedbackAboveWheel: !!wheel && wheel.get_parent() === parent &&
            siblings.indexOf(feedback) > siblings.indexOf(wheel),
            icons: feedback.get_children().filter(a => a.is_visible()).map(a => {
                const [x, y] = a.get_transformed_position();
                const [width, height] = a.get_transformed_size();
                return {x, y, width, height};
            })});
    }
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
    ObserveMotion() {
        if (this._paint) global.stage.disconnect(this._paint);
        this._frames = [];
        const start = GLib.get_monotonic_time();
        this._paint = global.stage.connect('after-paint', () => {
            if (this._frames.length >= 600) return;
            const extension = Main.extensionManager.lookup('citrica@genissonemilio.github.io')?.stateObj;
            if (!extension) return;
            const state = JSON.parse(extension.Status());
            this._frames.push({ms: (GLib.get_monotonic_time() - start) / 1000,
                animation: state.animation, selected: state.selected, motion: state.motion,
                closing: state.closing});
        });
    }
    Motion() {
        if (this._paint) global.stage.disconnect(this._paint);
        this._paint = 0;
        return JSON.stringify(this._frames ?? []);
    }
    StartRecordingAsync([path], invocation) {
        Gio.DBus.session.call('org.gnome.Shell.Screencast', '/org/gnome/Shell/Screencast',
            'org.gnome.Shell.Screencast', 'Screencast', new GLib.Variant('(sa{sv})',
                [path, {'framerate': new GLib.Variant('i', 60), 'draw-cursor': new GLib.Variant('b', true)}]),
            new GLib.VariantType('(bs)'), Gio.DBusCallFlags.NONE, 15000, null, (c, r) => {
                try {
                    const [ok, file] = c.call_finish(r).deep_unpack();
                    if (!ok) throw new Error('Native recorder did not start');
                    invocation.return_value(new GLib.Variant('(s)', [file]));
                } catch (e) { invocation.return_dbus_error('io.github.GenissonEmilio.Citrica.Test.Error', e.message); }
            });
    }
    StopRecordingAsync(_args, invocation) {
        Gio.DBus.session.call('org.gnome.Shell.Screencast', '/org/gnome/Shell/Screencast',
            'org.gnome.Shell.Screencast', 'StopScreencast', null, new GLib.VariantType('(b)'),
            Gio.DBusCallFlags.NONE, 15000, null, (c, r) => {
                try { invocation.return_value(c.call_finish(r)); }
                catch (e) { invocation.return_dbus_error('io.github.GenissonEmilio.Citrica.Test.Error', e.message); }
            });
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
    disable() {
        if (this._paint) global.stage.disconnect(this._paint);
        this.dbus.unexport(); Gio.bus_unown_name(this.bus); this.pointer = this.keyboard = null;
    }
}
