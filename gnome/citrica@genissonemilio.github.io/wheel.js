import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

export const SIZE = 380;
export const INNER = 66;
export const OUTER = 170;
export const LABEL_RADIUS = 122;
const C = SIZE / 2;
const TAU = Math.PI * 2;
const ICONS = {
    compress: 'view-restore-symbolic', target_size: 'zoom-fit-best-symbolic', crop: 'edit-cut-symbolic',
    adjust: 'preferences-color-symbolic', annotate: 'document-edit-symbolic',
    background: 'preferences-desktop-wallpaper-symbolic', redact: 'view-conceal-symbolic',
    redact_faces: 'avatar-default-symbolic', redact_text: 'insert-text-symbolic',
    metadata: 'dialog-information-symbolic', edit_metadata: 'document-properties-symbolic',
    strip: 'edit-clear-all-symbolic', images_pdf: 'application-pdf-symbolic', collage: 'view-grid-symbolic',
    qr: 'camera-photo-symbolic', trim: 'edit-cut-symbolic', speed: 'preferences-system-time-symbolic',
    split_media: 'view-dual-symbolic', join_media: 'insert-link-symbolic', snapshot: 'camera-photo-symbolic',
    normalize: 'audio-volume-high-symbolic', bleep: 'audio-volume-muted-symbolic',
    channels: 'audio-speakers-symbolic', merge_pdf: 'insert-link-symbolic', split_pdf: 'view-dual-symbolic',
    reorder_pdf: 'view-sort-ascending-symbolic', copy: 'edit-copy-symbolic', move: 'folder-symbolic',
    copy_path: 'insert-link-symbolic', terminal: 'utilities-terminal-symbolic', float: 'window-new-symbolic',
    share: 'network-transmit-symbolic',
};

export function pickSector(x, y, count) {
    const radius = Math.hypot(x - C, y - C);
    if (!count || radius <= INNER || radius > OUTER + 8) return -1;
    const angle = (Math.atan2(y - C, x - C) + Math.PI / 2 + TAU) % TAU;
    return Math.round(angle / TAU * count) % count;
}

function point(radius, angle) { return [C + radius * Math.cos(angle), C + radius * Math.sin(angle)]; }
function quadratic(cr, from, control, to) {
    cr.curveTo(from[0] + (control[0] - from[0]) * 2 / 3, from[1] + (control[1] - from[1]) * 2 / 3,
        to[0] + (control[0] - to[0]) * 2 / 3, to[1] + (control[1] - to[1]) * 2 / 3, ...to);
}

// Four rounded corners and two true circular arcs. The centre is transparent;
// this is an annular sector, not a rectangular button placed on a disk.
function sectorPath(cr, index, count) {
    const angle = -Math.PI / 2 + index * TAU / count;
    const half = Math.PI / count;
    const gap = 3, corner = 10;
    const oa = angle - half + gap / OUTER, ob = angle + half - gap / OUTER;
    const ia = angle - half + gap / INNER, ib = angle + half - gap / INNER;
    const od = corner / OUTER, id = corner / INNER;
    let p = point(INNER + corner, ia);
    cr.moveTo(...p);
    p = point(OUTER - corner, oa);
    cr.lineTo(...p);
    quadratic(cr, p, point(OUTER, oa), point(OUTER, oa + od));
    cr.arc(C, C, OUTER, oa + od, ob - od);
    p = point(OUTER, ob - od);
    quadratic(cr, p, point(OUTER, ob), point(OUTER - corner, ob));
    p = point(INNER + corner, ib);
    cr.lineTo(...p);
    quadratic(cr, p, point(INNER, ib), point(INNER, ib - id));
    cr.arcNegative(C, C, INNER, ib - id, ia + id);
    p = point(INNER, ia + id);
    quadratic(cr, p, point(INNER, ia), point(INNER + corner, ia));
    cr.closePath();
}

function canvas(draw) {
    const area = new St.DrawingArea({width: SIZE, height: SIZE, reactive: false});
    area.connect('repaint', widget => {
        const cr = widget.get_context();
        try { draw(cr); } finally { cr.$dispose(); }
    });
    return area;
}

export class WheelView {
    constructor({animations, activate, pick}) {
        this.animations = animations;
        this.actor = new St.Widget({width: SIZE, height: SIZE, reactive: true,
            layout_manager: new Clutter.FixedLayout(), accessible_name: 'Cítrica · roda de arquivos'});
        this.actor.set_pivot_point(.5, .5);
        this.actor.connect('button-release-event', (_actor, event) => {
            if (event.get_button() === 1) activate(...event.get_coords());
            return Clutter.EVENT_STOP;
        });
        const halo = canvas(cr => {
            cr.arc(C, C, OUTER + 8, 0, TAU);
            cr.arcNegative(C, C, INNER - 6, TAU, 0);
            cr.closePath();
            cr.setSourceRGBA(1, .89, .76, .24);
            cr.fill();
        });
        this.actor.add_child(halo);
        this._oldContents = new Set();
        this._segments = [];
        this._center = new St.Button({width: 116, height: 116, x: C - 58, y: C - 58,
            reactive: true, can_focus: true, accessible_name: 'Escolher arquivos',
            style: 'background-color:transparent;border-radius:58px;'});
        const middle = new St.Widget({width: 116, height: 116, layout_manager: new Clutter.FixedLayout()});
        this._preview = new St.Icon({icon_name: 'document-open-symbolic', icon_size: 42, x: 37, y: 19,
            style: 'color:#49372a;'});
        const pill = new St.Bin({width: 148, x: -16, y: 74,
            style: 'background-color:rgba(255,246,231,0.94);color:#291f1a;border-radius:17px;'
                + 'padding:7px 9px;font-size:11px;font-weight:600;'});
        this._pill = new St.Label({text: 'Arraste um arquivo', x_align: Clutter.ActorAlign.CENTER});
        pill.set_child(this._pill);
        this._pill.get_clutter_text().set_ellipsize(Pango.EllipsizeMode.END);
        middle.add_child(this._preview);
        middle.add_child(pill);
        this._center.set_child(middle);
        this._center.connect('clicked', pick);
        this.actor.add_child(this._center);
        this._hint = new St.Bin({width: SIZE,
            x: 0, y: SIZE - 5, reactive: false,
            style: 'color:#3b2e26;background-color:rgba(255,246,231,0.95);border-radius:14px;'
                + 'padding:6px;font-size:10px;'});
        this._hint.set_child(new St.Label({text: 'Solte um arquivo aqui · Esc para fechar',
            x_align: Clutter.ActorAlign.CENTER}));
        this.actor.add_child(this._hint);
        this.setInfo(null);
    }

    open() {
        if (!this.animations()) return;
        this.actor.opacity = 0;
        this.actor.scale_x = this.actor.scale_y = .88;
        this.actor.ease({opacity: 255, scale_x: 1, scale_y: 1, duration: 240,
            mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
    }

    setInfo(info, loading = false) {
        this._info = info;
        this._baseText = info?.count ? GLib.format_size(info.bytes ?? 0) :
            loading ? 'Carregando…' : 'Arraste um arquivo';
        this._pill.text = this._baseText;
        this._center.accessible_name = info?.label || 'Escolher arquivos';
        this._preview.icon_size = info?.count ? 64 : 42;
        this._preview.set_position(info?.count ? 26 : 37, info?.count ? 4 : 19);
        this._preview.gicon = info?.preview ? new Gio.FileIcon({file: Gio.File.new_for_path(info.preview)}) :
            new Gio.ThemedIcon({name: info?.icon || 'document-open-symbolic'});
        this._hint.visible = !info?.count && !loading;
    }

    render(items, {hasFiles = false, loading = false} = {}) {
        this._selected = -1;
        this._items = items;
        const previous = this._content;
        const content = new St.Widget({width: SIZE, height: SIZE, reactive: false,
            layout_manager: new Clutter.FixedLayout()});
        this._content = content;
        this.actor.insert_child_below(content, this._center);
        this._segments = [];
        const count = items.length || 8;
        for (let i = 0; i < count; i++) {
            const item = items[i];
            const group = new St.Widget({width: SIZE, height: SIZE, reactive: false,
                layout_manager: new Clutter.FixedLayout()});
            group.set_pivot_point(.5, .5);
            const draw = active => canvas(cr => {
                sectorPath(cr, i, count);
                const fill = new Cairo.LinearGradient(0, 0, SIZE, SIZE);
                if (active) {
                    fill.addColorStopRGBA(0, 1, .65, .30, .99);
                    fill.addColorStopRGBA(1, .98, .30, .10, .99);
                } else {
                    fill.addColorStopRGBA(0, 1, .94, .80, item ? .94 : .28);
                    fill.addColorStopRGBA(1, 1, .85, .80, item ? .94 : .28);
                }
                cr.setSource(fill);
                cr.fillPreserve();
                cr.setLineWidth(1);
                cr.setSourceRGBA(1, 1, 1, active ? .32 : .16);
                cr.stroke();
            });
            group.add_child(draw(false));
            const overlay = draw(true);
            overlay.opacity = 0;
            group.add_child(overlay);
            const angle = -Math.PI / 2 + i * TAU / count;
            if (item) {
                const labelGroup = new St.BoxLayout({width: 80,
                    x: C + LABEL_RADIUS * Math.cos(angle) - 40,
                    y: C + LABEL_RADIUS * Math.sin(angle) - (item.kind === 'format' ? 10 : 23),
                    style: 'spacing:3px;'});
                // GNOME 51 removed `vertical`; GNOME 46 predates `orientation`.
                if ('orientation' in labelGroup) labelGroup.orientation = Clutter.Orientation.VERTICAL;
                else labelGroup.vertical = true;
                if (item.kind !== 'format') labelGroup.add_child(new St.Icon({icon_size: 20,
                    x_align: Clutter.ActorAlign.CENTER,
                    icon_name: item.kind === 'page' ? 'view-more-symbolic' : ICONS[item.id] || 'document-properties-symbolic',
                    style: 'color:#2b211b;'}));
                const label = new St.Label({text: item.label.toUpperCase(),
                    x_align: Clutter.ActorAlign.CENTER,
                    style: `color:#251e1a;font-weight:700;text-align:center;font-size:${item.kind === 'format' ? 13 : 10}px;`});
                label.get_clutter_text().set_line_wrap(true);
                label.get_clutter_text().set_line_alignment(Pango.Alignment.CENTER);
                label.get_clutter_text().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);
                label.get_clutter_text().set_ellipsize(Pango.EllipsizeMode.NONE);
                labelGroup.add_child(label);
                group.add_child(labelGroup);
                content.add_child(group);
                // BoxLayout centres the label's natural width. A fixed 80px
                // label would leave its internal ClutterText aligned left.
                label.width = Math.min(80, label.get_preferred_width(-1)[1]);
            }
            if (!group.get_parent()) content.add_child(group);
            this._segments.push({group, overlay, angle});
            if (this.animations() && item) {
                group.opacity = 0;
                group.scale_x = group.scale_y = .92;
                group.translation_x = -12 * Math.cos(angle);
                group.translation_y = -12 * Math.sin(angle);
                group.ease({opacity: 255, scale_x: 1, scale_y: 1, translation_x: 0, translation_y: 0,
                    duration: 230, delay: i * 8, mode: Clutter.AnimationMode.EASE_OUT_BACK});
            }
        }
        if (previous) {
            this._oldContents.add(previous);
            if (this.animations()) previous.ease({opacity: 0, duration: 90, onComplete: () => {
                this._oldContents.delete(previous);
                previous.destroy();
            }});
            else { this._oldContents.delete(previous); previous.destroy(); }
        }
        this._hint.visible = !hasFiles;
        if (loading) this._pill.text = 'Carregando…';
        else this._pill.text = this._baseText;
    }

    select(index) {
        if (index === this._selected) return;
        const previous = this._selected;
        this._selected = index;
        this._pill.text = this._items[index]?.label || this._baseText;
        for (const i of new Set([previous, index])) {
            const sector = this._segments[i];
            if (!sector) continue;
            const active = i === index;
            const props = {translation_x: active ? 4 * Math.cos(sector.angle) : 0,
                translation_y: active ? 4 * Math.sin(sector.angle) : 0,
                scale_x: active ? 1.015 : 1, scale_y: active ? 1.015 : 1};
            if (this.animations()) {
                sector.overlay.ease({opacity: active ? 255 : 0, duration: 110,
                    mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
                sector.group.ease({...props, duration: 140, mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
            } else {
                sector.overlay.opacity = active ? 255 : 0;
                Object.assign(sector.group, props);
            }
        }
    }

    close(done) {
        this.actor.reactive = this._center.reactive = false;
        if (!this.animations()) { done(); return; }
        this.actor.remove_all_transitions();
        this.actor.ease({opacity: 0, scale_x: .94, scale_y: .94, duration: 130,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD, onComplete: done});
    }

    motionState() {
        return {settled: this.actor.opacity === 255 && Math.abs(this.actor.scale_x - 1) < .001 &&
            this._segments.every(s => s.group.opacity === 255 && !s.group.get_transition('opacity')),
        sectors: this._items?.length ?? 0, preview: !!this._info?.preview};
    }

    destroy() {
        this.actor.remove_all_transitions();
        for (const content of this._oldContents) {
            content.remove_all_transitions();
            content.destroy();
        }
        this._oldContents.clear();
        this.actor.destroy();
    }
}
