"""Small configuration and tool dialogs. File conversion lives in the GNOME wheel."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from citrica.desktop import SHELL_REVISION, SHELL_VERSION, desktop_call, extension_dir, extension_status, install_gnome
from citrica.gui import ICON, STYLE
from citrica.runtime import external_environment
from citrica.tools import TOOLS, execute

KEY_NAMES = {'Esc': 'Escape', 'Enter': 'Return', 'Return': 'Return', 'Space': 'space',
             'Backspace': 'BackSpace', 'Del': 'Delete', 'Ins': 'Insert', 'PgUp': 'Page_Up',
             'PgDown': 'Page_Down', 'Backtab': 'ISO_Left_Tab', 'Home': 'Home', 'End': 'End',
             'Left': 'Left', 'Right': 'Right', 'Up': 'Up', 'Down': 'Down', 'Tab': 'Tab',
             'Pause': 'Pause', 'Print': 'Print', 'Menu': 'Menu', 'CapsLock': 'Caps_Lock',
             'NumLock': 'Num_Lock', 'ScrollLock': 'Scroll_Lock', ',': 'comma', '.': 'period',
             '-': 'minus', '=': 'equal', '/': 'slash', '\\': 'backslash', '[': 'bracketleft',
             ']': 'bracketright', ';': 'semicolon', "'": 'apostrophe', '`': 'grave'}


def readable_shortcut(accelerator):
    import re
    modifiers = {'Super': 'Super', 'Control': 'Ctrl', 'Alt': 'Alt', 'Shift': 'Shift'}
    mods = [modifiers.get(m, m) for m in re.findall(r'<([^>]+)>', accelerator)]
    key = accelerator.rsplit('>', 1)[-1]
    reverse = {value: name for name, value in KEY_NAMES.items()}
    key = reverse.get(key, key.upper() if len(key) == 1 else key)
    return '+'.join([*mods, key])


class ImageSelection(QLabel):
    selected = Signal(str)

    def __init__(self, path):
        super().__init__()
        from PIL import Image, ImageOps
        from PIL.ImageQt import ImageQt
        with Image.open(path) as im:
            preview = ImageOps.exif_transpose(im).convert('RGBA')
            self.source_size = preview.size
            self.pixmap_source = QPixmap.fromImage(ImageQt(preview)).scaled(
                440, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(self.pixmap_source.size())
        self.start = self.end = None
        self.setToolTip('Arraste sobre a foto para escolher a área. O original será preservado.')

    def mousePressEvent(self, event):
        self.start = self.end = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        self.end = event.position().toPoint()
        rect = QRect(self.start, self.end).normalized().intersected(self.rect())
        sx, sy = self.source_size[0]/self.width(), self.source_size[1]/self.height()
        x, y = int(rect.x()*sx), int(rect.y()*sy)
        w, h = max(1, int(rect.width()*sx)), max(1, int(rect.height()*sy))
        w, h = min(w, self.source_size[0]-x), min(h, self.source_size[1]-y)
        self.selected.emit(f'{x},{y},{w},{h}')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(QPoint(0, 0), self.pixmap_source)
        if self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor('#ed713d'), 2))
            painter.setBrush(QColor(237, 113, 61, 50))
            painter.drawRect(QRect(self.start, self.end).normalized())


def show_wheel(paths):
    quoted = '[' + ','.join(json.dumps(str(Path(p).resolve())) for p in paths) + ']'
    result = desktop_call('Show', quoted, 'convert')
    if result.returncode:
        raise RuntimeError('A integração GNOME ainda não está ativa. Abra as configurações do Cítrica.')


def shell_settings(key, value=None):
    script = """import gi,json,sys
from gi.repository import Gio
source=Gio.SettingsSchemaSource.new_from_directory(sys.argv[1],Gio.SettingsSchemaSource.get_default(),False)
schema=source.lookup('org.gnome.shell.extensions.citrica',False)
settings=Gio.Settings.new_full(schema,None,None)
key=sys.argv[2]
if len(sys.argv)>3:
 value=json.loads(sys.argv[3])
 if key=='toggle-wheel': settings.set_strv(key,value)
 elif key=='animations': settings.set_boolean(key,value)
 else: settings.set_string(key,value)
 Gio.Settings.sync()
else:
 print(json.dumps(settings.get_value(key).unpack()))
"""
    args = ['/usr/bin/python3', '-c', script, str(extension_dir() / 'schemas'), key]
    if value is not None:
        args += [json.dumps(value)]
    result = subprocess.run(args, capture_output=True, text=True, check=True, env=external_environment())
    return json.loads(result.stdout) if value is None else None


def validate_shortcut(text):
    import re
    from PySide6.QtGui import QKeySequence
    parts = [p.strip() for p in text.split('+')]
    modifiers = {'super': '<Super>', 'ctrl': '<Control>', 'alt': '<Alt>', 'shift': '<Shift>'}
    if len(parts) < 2 or not any(p.lower() in {'super', 'ctrl', 'alt'} for p in parts[:-1]):
        raise ValueError('Use Super, Ctrl ou Alt e uma tecla. Exemplo: Super+Shift+C.')
    if any(p.lower() not in modifiers for p in parts[:-1]) or not parts[-1] or parts[-1].lower() in modifiers:
        raise ValueError('Atalho inválido.')
    if len({p.lower() for p in parts[:-1]}) != len(parts[:-1]):
        raise ValueError('Não repita um modificador.')
    sequence = QKeySequence.fromString(parts[-1])
    if sequence.count() != 1 or sequence[0].key() == Qt.Key.Key_unknown:
        raise ValueError('Tecla inválida.')
    name = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if name in KEY_NAMES:
        key = KEY_NAMES[name]
    elif len(name) == 1 and name.isascii() and name.isalnum():
        key = name.lower()
    elif re.fullmatch(r'F(?:[1-9]|[12][0-9]|3[0-5])', name):
        key = name
    else:
        raise ValueError('Use letra A–Z, número, F1–F35 ou uma tecla de navegação.')
    accelerator = ''.join(modifiers[p.lower()] for p in parts[:-1]) + key
    # Check existing GNOME and user custom bindings without changing any of them.
    listing = subprocess.run(['gsettings', 'list-recursively'], capture_output=True, text=True, timeout=15,
                             env=external_environment())
    def normalized(value):
        aliases = {'control': 'ctrl', 'primary': 'ctrl', 'mod4': 'super'}
        mods = frozenset(aliases.get(m.lower(), m.lower()) for m in re.findall(r'<([^>]+)>', value))
        return mods, re.sub(r'<[^>]+>', '', value).lower()
    for line in listing.stdout.splitlines():
        if 'org.gnome.shell.extensions.citrica' in line:
            continue
        if any(normalized(key) == normalized(accelerator) for key in re.findall(r"'([^']+)'", line)):
            raise ValueError('Este atalho já é usado pelo GNOME. Escolha outra combinação.')
    return accelerator


class Settings(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Cítrica · configurações')
        self.resize(560, 440)
        layout = QVBoxLayout(self)
        title = QLabel('Cítrica · direto no seu arquivo')
        title.setStyleSheet('font-size:23px;font-weight:bold;')
        layout.addWidget(title)
        note = QLabel('Arraste um arquivo, pressione Shift e solte no formato.\n'
                      'Alt abre ferramentas. Ctrl abre ações. Esc fecha a roda.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.shortcut = QLineEdit('Super+Shift+C')
        self.shortcut.setAccessibleName('Atalho global para mostrar a roda')
        form.addRow('Mostrar a roda', self.shortcut)
        self.modifier = QComboBox()
        self.modifier.addItems(['Shift', 'Super'])
        form.addRow('Durante o arraste', self.modifier)
        self.animations = QCheckBox('Animar a abertura da roda')
        self.animations.setChecked(True)
        form.addRow('', self.animations)
        layout.addLayout(form)
        self.install = QPushButton('Instalar integração GNOME neste usuário')
        self.install.clicked.connect(self.install_extension)
        layout.addWidget(self.install)
        row = QHBoxLayout()
        save = QPushButton('Salvar atalho e preferências')
        save.clicked.connect(self.save)
        row.addWidget(save)
        test = QPushButton('Testar roda agora')
        test.clicked.connect(self.test)
        row.addWidget(test)
        layout.addLayout(row)
        details = QLabel('As conversões acontecem no desktop. Esta janela serve apenas para configurar.\n'
                         'A integração global desta versão é para GNOME 50 / Wayland.')
        details.setWordWrap(True)
        layout.addWidget(details)
        self.refresh()

    def refresh(self):
        state = extension_status()
        active = state.get('version') == SHELL_VERSION and state.get('revision') == SHELL_REVISION
        if state.get('version') and not active:
            self.status.setText('● Atualização instalada · o GNOME ainda executa a revisão anterior. '
                                'Saia e entre na sessão para carregar a roda nova.')
        else:
            self.status.setText('● Integração ativa · roda disponível no desktop' if active else
                                '○ Integração ainda não carregada nesta sessão. Instale e entre novamente no GNOME.')
        if (extension_dir() / 'schemas/gschemas.compiled').exists():
            try:
                key = shell_settings('toggle-wheel')[0]
                self.shortcut.setText(readable_shortcut(key))
                self.modifier.setCurrentIndex(1 if shell_settings('drag-key') == 'super' else 0)
                self.animations.setChecked(shell_settings('animations'))
            except Exception:
                pass

    def install_extension(self):
        try:
            result = install_gnome()
            self.refresh()
            if result['requires_login']:
                QMessageBox.information(self, 'Integração instalada',
                                        'O GNOME precisa carregar a nova extensão. Saia e entre novamente na sessão.\n'
                                        'O atalho Super+Shift+C já foi configurado na extensão.')
        except Exception as e:
            QMessageBox.warning(self, 'Falha na integração', str(e))

    def save(self):
        try:
            accelerator = validate_shortcut(self.shortcut.text())
            if not (extension_dir() / 'schemas/gschemas.compiled').exists():
                raise ValueError('Instale a integração GNOME primeiro.')
            shell_settings('toggle-wheel', [accelerator])
            shell_settings('drag-key', 'super' if self.modifier.currentIndex() else 'shift')
            shell_settings('animations', self.animations.isChecked())
            self.status.setText('Preferências salvas. Use o atalho ou arraste um arquivo e pressione a tecla configurada.')
        except Exception as e:
            QMessageBox.warning(self, 'Verifique o atalho', str(e))

    def test(self):
        try:
            show_wheel([])
            self.close()
        except Exception as e:
            QMessageBox.information(self, 'Roda indisponível', str(e))


class ToolWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, tool, paths, params):
        super().__init__()
        self.tool, self.paths, self.params = tool, paths, params
        self.cancel = threading.Event()

    def run(self):
        try:
            self.done.emit(execute(self.tool, self.paths, self.params, cancel=self.cancel))
        except Exception as e:
            self.failed.emit(str(e))


class Shelf(QDialog):
    """A compact file shelf, without the converter window or a persistent drop window."""
    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.setWindowTitle('Cítrica · prateleira')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Arraste para outro aplicativo:'))
        for path in paths:
            item = QPushButton(path.name)
            item.pressed.connect(self.drag_files)
            layout.addWidget(item)

    def drag_files(self):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in self.paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class ToolDialog(QDialog):
    def __init__(self, tool, paths):
        super().__init__()
        self.tool, self.paths, self.worker = tool, paths, None
        self.setWindowTitle('Cítrica · ' + TOOLS[tool]['label'])
        self.resize(520, 180)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{TOOLS[tool]['label']} · {len(paths)} arquivo(s)"))
        form = QFormLayout()
        self.fields = {}
        for key, title, default in TOOLS[tool]['fields']:
            field = QLineEdit(default)
            form.addRow(title, field)
            self.fields[key] = field
        layout.addLayout(form)
        from citrica.core import family
        if paths and family(paths[0]) == 'image' and tool in {'crop', 'redact', 'annotate'}:
            self.canvas = ImageSelection(paths[0])
            def select_area(rect):
                if 'rect' in self.fields:
                    self.fields['rect'].setText(rect)
                if 'position' in self.fields:
                    self.fields['position'].setText(','.join(rect.split(',')[:2]))
            self.canvas.selected.connect(select_area)
            layout.addWidget(QLabel('Arraste na foto para selecionar a área:' if tool != 'annotate' else
                                    'Clique na foto para posicionar o texto:'))
            layout.addWidget(self.canvas)
        self.message = QLabel('Uma nova cópia será criada. O original será preservado.')
        self.message.setWordWrap(True)
        if tool == 'target_size':
            self.message.setText('Saída: WebP para imagens, MP3 para áudio, MP4 para vídeo. '
                                 'Imagens podem ter a resolução reduzida para caber no limite.')
        elif tool in {'redact_faces', 'redact_text'}:
            self.message.setText('Detecção local automática. Revise a cópia antes de compartilhar; '
                                 'a detecção pode deixar áreas sem identificar.')
        layout.addWidget(self.message)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.hide()
        layout.addWidget(self.output)
        self.open_output = QPushButton('Abrir resultado')
        self.latest_output = None
        self.open_output.clicked.connect(self.open_result)
        self.open_output.hide()
        layout.addWidget(self.open_output)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText('Executar')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        self.buttons.rejected.connect(self.close)
        layout.addWidget(self.buttons)

    def apply(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = ToolWorker(self.tool, self.paths, {k: v.text() for k, v in self.fields.items()})
        self.worker.done.connect(self.tool_done)
        self.worker.failed.connect(lambda e: self.message.setText('Falha: ' + e))
        self.worker.finished.connect(lambda: self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True))
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)
        self.message.setText('Processando localmente…')
        self.worker.start()

    def tool_done(self, result):
        if 'text' in result:
            self.output.setPlainText(result['text'])
            self.output.show()
            self.resize(600, 450)
            self.message.setText('Resultado local; você pode selecionar e copiar o texto.')
        else:
            self.message.setText('Concluído.\n' + '\n'.join(str(p) for p in result['outputs']))
            if result['outputs']:
                self.latest_output = result['outputs'][0]
                self.open_output.show()

    def open_result(self):
        if self.latest_output:
            subprocess.Popen(['xdg-open', str(self.latest_output)], env=external_environment())

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.message.setText('Cancelando…')
            event.ignore()
        else:
            event.accept()

    def reject(self):
        # QDialog handles Escape through reject(), bypassing closeEvent(). Keep
        # the worker alive until it has stopped and cleaned up its temporary data.
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.message.setText('Cancelando…')
            return
        super().reject()


def file_action(tool, paths):
    app = QApplication.instance()
    if tool == 'copy_path':
        app.clipboard().setText('\n'.join(str(p) for p in paths))
    elif tool == 'copy':
        mime = QMimeData()
        urls = [QUrl.fromLocalFile(str(p)) for p in paths]
        mime.setUrls(urls)
        mime.setData('x-special/gnome-copied-files', ('copy\n' + '\n'.join(u.toString() for u in urls)).encode())
        app.clipboard().setMimeData(mime)
        # Clipboard ownership must remain alive until the user pastes or replaces it.
        from PySide6.QtCore import QTimer
        timer = QTimer(app)
        timer.timeout.connect(lambda: app.quit() if not app.clipboard().ownsClipboard() else None)
        timer.start(1000)
        return 'resident'
    elif tool == 'terminal':
        directory = str(paths[0] if paths[0].is_dir() else paths[0].parent)
        if shutil.which('ptyxis'):
            subprocess.Popen(['ptyxis', '--standalone', '--new-window', '--working-directory', directory],
                             env=external_environment())
        elif shutil.which('gnome-terminal'):
            subprocess.Popen(['gnome-terminal', '--working-directory', directory], env=external_environment())
        else:
            raise ValueError('Nenhum terminal compatível encontrado.')
    elif tool == 'move':
        target = QFileDialog.getExistingDirectory(None, 'Mover originais para')
        if not target:
            return
        from citrica.core import publish
        for path in paths:
            if path.parent == Path(target).resolve():
                continue
            import tempfile
            with tempfile.TemporaryDirectory(prefix='.citrica-', dir=target) as folder:
                staged = Path(folder) / path.name
                shutil.copy2(path, staged)
                publish(staged, Path(target) / path.name)
                path.unlink()
    elif tool == 'share':
        executable = shutil.which('localsend')
        if not executable:
            raise ValueError('Instale LocalSend para compartilhar no Linux. AirDrop é exclusivo da Apple.')
        subprocess.Popen([executable, *map(str, paths)], env=external_environment())
    return None


def launch_companion(args):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Cítrica')
    app.setWindowIcon(QIcon(str(ICON)))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    paths = [p.expanduser().resolve() for p in args.files]
    if args.pick:
        files, _ = QFileDialog.getOpenFileNames(None, 'Escolher arquivos para a roda')
        if files:
            show_wheel(files)
        return 0
    if args.tool:
        if args.tool not in TOOLS:
            QMessageBox.warning(None, 'Ferramenta inválida', args.tool)
            return 1
        if TOOLS[args.tool].get('actions'):
            try:
                if args.tool == 'float':
                    window = Shelf(paths)
                    window.show()
                    return app.exec()
                result = file_action(args.tool, paths)
                if result == 'resident':
                    return app.exec()
                if args.tool == 'copy_path':
                    # Qt's Wayland clipboard needs an owner; use a tiny message dialog
                    # while the user pastes, instead of destroying the selection.
                    QMessageBox.information(None, 'Caminhos copiados', 'Caminhos copiados. Cole no destino e feche esta mensagem.')
                return 0
            except Exception as e:
                QMessageBox.warning(None, 'Cítrica', str(e))
                return 1
        window = ToolDialog(args.tool, paths)
    else:
        window = Settings()
    window.show()
    if args.screenshot:
        from PySide6.QtCore import QTimer
        def capture():
            window.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(400, capture)
    return app.exec()
