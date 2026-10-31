import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {THEMES, getTheme} from './themes.js';

function preview(cr, width, height, theme) {
    // The same five palette/opacity/outline definitions as the desktop wheel.
    const scale = Math.min(width / 380, height / 380);
    cr.translate((width - 380 * scale) / 2, (height - 380 * scale) / 2);
    cr.scale(scale, scale);
    cr.setSourceRGB(.82, .86, .90);
    cr.paint();
    cr.setSourceRGBA(...theme.halo);
    cr.arc(190, 190, 178, 0, Math.PI * 2);
    cr.arcNegative(190, 190, 60, Math.PI * 2, 0);
    cr.fill();
    for (let i = 0; i < 5; i++) {
        cr.newPath();
        const angle = -Math.PI / 2 + i * Math.PI * 2 / 5;
        const start = angle - Math.PI / 5 + .025, end = angle + Math.PI / 5 - .025;
        cr.arc(190, 190, 170, start, end);
        cr.arcNegative(190, 190, 66, end, start);
        cr.closePath();
        const a = i === 1 ? theme.selected_start : theme.start;
        const b = i === 1 ? theme.selected_end : theme.end;
        cr.setSourceRGBA(...a.map((value, index) => (value + b[index]) / 2));
        cr.fillPreserve();
        cr.setLineWidth(theme.border_width);
        cr.setSourceRGBA(...theme.border);
        cr.stroke();
        const x = 190 + 122 * Math.cos(angle), y = 190 + 122 * Math.sin(angle);
        if (theme.label_chip) {
            cr.rectangle(x - 31, y - 14, 62, 28);
            cr.setSourceRGBA(...theme.label_chip);
            cr.fill();
        }
        cr.selectFontFace('Sans', 0, 1);
        cr.setFontSize(13);
        cr.setSourceRGBA(...(i === 1 ? theme.active_text : theme.text));
        const text = ['PNG', 'JPG', 'WEBP', 'PDF', 'AVIF'][i];
        const extents = cr.textExtents(text);
        cr.moveTo(x - extents.width / 2 - extents.xBearing, y + 5);
        cr.showText(text);
    }
}

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

        const settings = this.getSettings();
        const appearance = new Adw.PreferencesPage({title: 'Aparência', icon_name: 'applications-graphics-symbolic'});
        const styles = new Adw.PreferencesGroup({title: 'Personalizar a roda',
            description: 'Cinco acabamentos. As posições, animações, miniatura e ações são preservadas.'});
        const model = Gtk.StringList.new(THEMES.map(theme => theme.name));
        const selector = new Adw.ComboRow({title: 'Estilo da roda', model,
            selected: Math.max(0, THEMES.findIndex(theme => theme.id === settings.get_string('wheel-theme')))});
        const canvas = new Gtk.DrawingArea({content_width: 330, content_height: 330,
            halign: Gtk.Align.CENTER, margin_top: 16, margin_bottom: 12});
        canvas.set_draw_func((_area, cr, width, height) => preview(cr, width, height,
            getTheme(settings.get_string('wheel-theme'))));
        const description = new Gtk.Label({label: getTheme(settings.get_string('wheel-theme')).description,
            wrap: true, margin_bottom: 12, margin_start: 12, margin_end: 12});
        selector.connect('notify::selected', () => {
            const theme = THEMES[selector.selected];
            if (theme) settings.set_string('wheel-theme', theme.id);
        });
        const changed = settings.connect('changed::wheel-theme', () => {
            const theme = getTheme(settings.get_string('wheel-theme'));
            selector.selected = THEMES.findIndex(item => item.id === theme.id);
            description.label = theme.description;
            canvas.queue_draw();
        });
        window.connect('close-request', () => { settings.disconnect(changed); return false; });
        styles.add(selector);
        styles.add(canvas);
        styles.add(description);
        const note = new Adw.ActionRow({title: 'Transparência sem perder a leitura',
            subtitle: 'Aquarela e Vidro claro mostram o desktop, com fundo próprio nos rótulos.'});
        styles.add(note);
        appearance.add(styles);
        window.add(appearance);
    }
}
