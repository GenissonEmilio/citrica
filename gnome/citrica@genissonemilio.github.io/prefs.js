import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class Preferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage({title: 'Cítrica', icon_name: 'preferences-system-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Roda global no desktop',
            description: 'Arraste um arquivo e pressione Shift. Alt: ferramentas. Ctrl: ações.'});
        const row = new Adw.ActionRow({title: 'Atalhos e preferências',
            subtitle: 'Configure a combinação global, tecla de arraste e animação.'});
        const button = new Gtk.Button({label: 'Abrir configurações', valign: Gtk.Align.CENTER});
        button.connect('clicked', () => {
            const path = GLib.build_filenamev([GLib.get_user_config_dir(), 'citrica', 'desktop.json']);
            const [, bytes] = Gio.File.new_for_path(path).load_contents(null);
            const config = JSON.parse(new TextDecoder().decode(bytes));
            Gio.Subprocess.new([...config.command, '--settings'], Gio.SubprocessFlags.NONE);
            window.close();
        });
        row.add_suffix(button);
        group.add(row);
        page.add(group);
        window.add(page);
    }
}
