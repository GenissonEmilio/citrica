"""Resident Windows app, tray, preferences, IPC and asynchronous wheel actions."""
import json
import logging
import platform
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout,
)

from citrica import __version__
from citrica.companion import Shelf, ToolDialog, file_action
from citrica.core import convert, dependencies
from citrica.desktop import request
from citrica.gui import ICON, STYLE
from citrica.windows import config
from citrica.windows.ipc import MAX_REQUEST, send, server_name
from citrica.windows.wheel import CENTER, SIZE, Wheel


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation, self.cancel = operation, threading.Event()

    def run(self):
        try:
            self.result.emit(self.operation(self.cancel))
        except Exception as error:
            logging.getLogger('citrica').exception('Operação local falhou')
            self.failed.emit(str(error))


class Settings(QDialog):
    def __init__(self, desktop):
        super().__init__()
        self.desktop = desktop
        self.setWindowTitle('Cítrica · configurações')
        self.resize(560, 430)
        layout = QVBoxLayout(self)
        title = QLabel('Cítrica · direto no seu arquivo')
        title.setStyleSheet('font-size:23px;font-weight:bold;')
        layout.addWidget(title)
        note = QLabel('Arraste um arquivo no Explorer e pressione Shift.\n'
                      'Alt: ferramentas · Ctrl: ações · Esc: cancelar.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel('O Cítrica continua na bandeja ao fechar esta janela.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.shortcut = QLineEdit(desktop.settings['shortcut'])
        self.shortcut.setAccessibleName('Atalho global para mostrar a roda')
        form.addRow('Mostrar a roda', self.shortcut)
        self.modifier = QComboBox()
        self.modifier.addItems(['Shift', 'Win'])
        self.modifier.setCurrentText(desktop.settings['drag_key'])
        form.addRow('Durante o arraste', self.modifier)
        self.animations = QCheckBox('Animar a roda')
        self.animations.setChecked(desktop.settings['animations'])
        form.addRow('', self.animations)
        self.startup = QCheckBox('Iniciar na bandeja ao entrar no Windows')
        self.startup.setChecked(config.startup_enabled() if sys.platform == 'win32' else False)
        form.addRow('', self.startup)
        layout.addLayout(form)
        row = QHBoxLayout()
        save = QPushButton('Salvar preferências')
        save.clicked.connect(self.save)
        test = QPushButton('Testar roda agora')
        test.clicked.connect(self.test)
        row.addWidget(save)
        row.addWidget(test)
        layout.addLayout(row)
        diagnostics = QPushButton('Salvar diagnóstico para suporte')
        diagnostics.clicked.connect(self.diagnostics)
        layout.addWidget(diagnostics)
        info = dependencies()
        details = QLabel('Processamento local · originais preservados.\n'
                         f"FFmpeg: {'disponível' if info['ffmpeg'] else 'não encontrado'} · "
                         f"LibreOffice: {'disponível' if info['libreoffice'] else 'opcional, não encontrado'}")
        details.setWordWrap(True)
        layout.addWidget(details)

    def save(self):
        try:
            self.desktop.apply_settings({'shortcut': self.shortcut.text().strip(),
                'drag_key': self.modifier.currentText(), 'animations': self.animations.isChecked()})
            if sys.platform == 'win32':
                config.set_startup(self.startup.isChecked())
            self.status.setText('Preferências salvas. O atalho e a tecla de arraste já estão ativos.')
        except Exception as error:
            QMessageBox.warning(self, 'Verifique as preferências', str(error))

    def test(self):
        self.hide()
        self.desktop.show_wheel([])

    def diagnostics(self):
        name, _ = QFileDialog.getSaveFileName(self, 'Salvar diagnóstico',
                                              str(Path.home() / 'citrica-diagnostico.json'), 'JSON (*.json)')
        if name:
            data = {'version': __version__, 'platform': platform.platform(),
                    'dependencies': dependencies(), 'desktop': self.desktop.status(),
                    'preferences': self.desktop.settings}
            data['desktop'].pop('paths', None)
            Path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            self.status.setText('Diagnóstico salvo.')


class Desktop(QObject):
    def __init__(self, app, native_factory=None, listen=True):
        super().__init__()
        self.app, self.settings = app, config.load()
        self.paths, self.palette, self.mode, self.page = [], None, 'convert', 0
        self.generation, self.busy, self.active, self.dragging = 0, False, False, False
        self.jobs, self.windows = set(), set()
        self.counts = {'converted': 0, 'errors': 0}
        self.last_message, self.hotkey_error = '', ''
        self._quitting = False
        self.wheel = Wheel(lambda: self.settings['animations'])
        self.wheel.filesOffered.connect(self.offer)
        self.wheel.chosen.connect(self.apply)
        self.wheel.cancelled.connect(self.hide_wheel)
        self.wheel.pickFiles.connect(self.pick)
        if native_factory is None:
            from citrica.windows.native import NativeDesktop
            native_factory = NativeDesktop
        self.native = native_factory(app, self.settings)
        self.native.toggle.connect(self.toggle)
        self.native.mode.connect(self.drag_mode)
        self.native.released.connect(self.release)
        self.native.key.connect(lambda key: self.wheel.keyboard(key, QCursor.pos()))
        try:
            self.native.register(self.settings['shortcut'])
        except ValueError as error:
            self.hotkey_error = str(error)
        self.tray = QSystemTrayIcon(QIcon(str(ICON)), self)
        self.tray.setToolTip('Cítrica · arraste e pressione Shift')
        menu = QMenu()
        for title, action in [('Mostrar roda', lambda: self.show_wheel([])), ('Escolher arquivos', self.pick),
                              ('Configurações', self.show_settings), ('Sair', self.quit)]:
            item = QAction(title, menu)
            item.triggered.connect(action)
            menu.addAction(item)
        self.tray.setContextMenu(menu)
        self.menu = menu
        self.tray.activated.connect(lambda reason: self.show_settings()
                                   if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        if listen and not self.server.listen(server_name()):
            raise RuntimeError('Já existe uma instância do Cítrica. Aguarde e tente novamente.')
        self.pointer_timer = QTimer(self)
        self.pointer_timer.timeout.connect(lambda: self.wheel.pointer(QCursor.pos()) if self.active else None)
        self.pointer_timer.start(20)

    def _accept(self):
        socket = self.server.nextPendingConnection()
        buffer = bytearray()
        def read():
            buffer.extend(bytes(socket.readAll()))
            if len(buffer) > MAX_REQUEST:
                socket.abort()
                return
            if b'\n' not in buffer:
                return
            try:
                result = self.dispatch(json.loads(buffer.split(b'\n', 1)[0]))
            except Exception as error:
                result = {'error': str(error)}
            socket.write(json.dumps(result, ensure_ascii=False).encode('utf-8') + b'\n')
            socket.disconnectFromServer()
        socket.readyRead.connect(read)
        socket.disconnected.connect(socket.deleteLater)
        if socket.bytesAvailable():
            read()

    def dispatch(self, payload):
        op = payload.get('op')
        if op == 'status':
            return self.status()
        if op == 'show':
            paths = payload.get('paths', [])
            if not isinstance(paths, list) or len(paths) > 1000 or not all(isinstance(p, str) for p in paths):
                raise ValueError('Seleção inválida.')
            self.show_wheel([Path(p).resolve() for p in paths])
        elif op == 'pick':
            QTimer.singleShot(0, self.pick)
        elif op == 'settings':
            QTimer.singleShot(0, self.show_settings)
        elif op == 'quit':
            QTimer.singleShot(0, self.quit)
        else:
            raise ValueError('Comando desconhecido.')
        return {'ok': True}

    def status(self):
        return {'platform': 'windows', 'version': __version__, 'visible': self.active,
                'paths': [str(p) for p in self.paths], 'items': self.wheel.items,
                'selection': self.wheel.info, 'selected': self.wheel.selected,
                'cachedSelection': self.palette is not None, 'dragging': self.dragging,
                'busy': self.busy, 'mode': self.mode, 'counts': dict(self.counts),
                'shortcut': self.settings['shortcut'], 'hotkey_active': not bool(self.hotkey_error),
                'hotkey_error': self.hotkey_error, 'last_message': self.last_message}

    def job(self, operation, done, failed=None):
        job = Job(operation)
        self.jobs.add(job)
        job.result.connect(done)
        job.failed.connect(failed or (lambda error: self.notify('Cítrica · falha', error)))
        job.finished.connect(lambda: self.jobs.discard(job))
        job.finished.connect(job.deleteLater)
        job.start()

    def notify(self, title, message):
        self.last_message = message
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)

    def toggle(self):
        if self.active:
            self.hide_wheel()
        else:
            self.show_wheel([])

    def show_wheel(self, paths, mode='convert', dragging=False):
        if self.busy or self._quitting:
            self.notify('Cítrica', 'Aguarde a conversão em andamento.')
            return
        paths = list(dict.fromkeys(Path(p).resolve() for p in paths))
        if len(paths) > 1000 or any(not p.is_file() for p in paths):
            self.notify('Cítrica', 'Selecione até 1000 arquivos locais existentes.')
            return
        changed = paths != self.paths
        if changed or not self.active:
            self.generation += 1
            self.palette = None
            self.wheel.clear()
        self.paths, self.mode, self.dragging, self.page = paths, mode, dragging, 0
        if not self.active:
            cursor = QCursor.pos()
            screen = self.app.screenAt(cursor) or self.app.primaryScreen()
            rect = screen.availableGeometry()
            position = QPoint(max(rect.left(), min(cursor.x()-CENTER, rect.right()-SIZE+1)),
                              max(rect.top(), min(cursor.y()-CENTER, rect.bottom()-SIZE-35)))
            self.wheel.present(position)
        self.active = self.native.visible = True
        if self.palette:
            self.render()
        elif paths:
            self.load_palette()

    def load_palette(self):
        token, paths = self.generation, list(self.paths)
        def done(palette):
            if token != self.generation or not self.active:
                return
            self.palette = palette
            self.render()
        def failed(error):
            if token == self.generation and self.active:
                self.hide_wheel()
                self.notify('Cítrica · seleção inválida', error)
        self.job(lambda _cancel: request({'op': 'palette', 'paths': [str(p) for p in paths]}), done, failed)

    def render(self):
        if not self.palette:
            return
        items = self.palette['modes'].get(self.mode, [])
        pages = max(1, math_ceil(len(items), 7))
        if pages > 1:
            current = items[self.page*7:self.page*7+7] + [{'id': str((self.page+1) % pages),
                'label': f'Mais · {self.page+1}/{pages}', 'kind': 'page'}]
        else:
            current = items
        self.wheel.set_palette(self.paths, current, self.palette['selection'])
        if not items:
            self.notify('Cítrica', 'Nenhuma operação disponível para este tipo de arquivo.')

    def offer(self, paths):
        if paths != self.paths:
            self.show_wheel(paths, self.mode, dragging=True)
        else:
            self.dragging = True

    def drag_mode(self, mode):
        if not self.active:
            self.show_wheel([], mode, dragging=True)
        elif mode != self.mode:
            self.mode, self.page = mode, 0
            self.render()

    def release(self):
        token = self.generation
        # OLE may dispatch Drop just after the physical button-up. Let its
        # validated file offer commit first, then dismiss unhandled releases.
        QTimer.singleShot(250, lambda: self.hide_wheel() if token == self.generation and
                          self.dragging and not self.native.left_down() else None)

    def hide_wheel(self):
        self.generation += 1
        self.paths, self.palette, self.dragging, self.active = [], None, False, False
        self.page = 0
        self.native.visible = False
        self.native.reset_drag()
        self.wheel.dismiss()

    def apply(self, item):
        if item['kind'] == 'page':
            self.page = int(item['id'])
            self.render()
            return
        paths = list(self.paths)
        self.hide_wheel()
        if not paths:
            return
        if item['kind'] == 'tool':
            try:
                if item['id'] == 'float':
                    self.keep_window(Shelf(paths))
                elif item['id'] in {'copy', 'copy_path', 'terminal', 'move', 'share'}:
                    file_action(item['id'], paths)
                else:
                    self.keep_window(ToolDialog(item['id'], paths))
            except Exception as error:
                self.notify('Cítrica · falha', str(error))
            return
        self.busy = True
        self.notify('Cítrica', f"Convertendo {len(paths)} arquivo(s) para {item['label']}…")
        def work(cancel):
            outputs, errors = [], []
            for path in paths:
                try:
                    outputs.extend(convert(path, item['id'], cancel=cancel))
                except Exception as error:
                    errors.append(f'{path.name}: {error}')
            return {'outputs': outputs, 'errors': errors}
        def done(result):
            self.busy = False
            self.counts['converted'] += len(result['outputs'])
            self.counts['errors'] += len(result['errors'])
            self.notify('Cítrica · falha' if result['errors'] else 'Cítrica · concluído',
                        '\n'.join(result['errors']) if result['errors'] else
                        f"{len(result['outputs'])} arquivo(s) salvo(s) junto ao original.")
        def failed(error):
            self.busy = False
            self.counts['errors'] += 1
            self.notify('Cítrica · falha', error)
        self.job(work, done, failed)

    def keep_window(self, window):
        self.windows.add(window)
        window.finished.connect(lambda: self.windows.discard(window))
        window.show()
        window.raise_()
        window.activateWindow()

    def show_settings(self):
        if self.hotkey_error:
            self.notify('Cítrica · atalho indisponível', self.hotkey_error)
        existing = next((w for w in self.windows if isinstance(w, Settings)), None)
        if existing:
            existing.show()
            existing.raise_()
            existing.activateWindow()
        else:
            self.keep_window(Settings(self))

    def pick(self):
        self.hide_wheel()
        names, _ = QFileDialog.getOpenFileNames(None, 'Escolher arquivos para a roda')
        if names:
            self.show_wheel([Path(name) for name in names])

    def apply_settings(self, settings):
        previous = dict(self.settings)
        self.native.register(settings['shortcut'])
        try:
            config.save(settings)
        except Exception:
            self.native.register(previous['shortcut'])
            raise
        self.settings.update(settings)
        self.hotkey_error = ''

    def quit(self):
        self._quitting = True
        self.hide_wheel()
        for job in self.jobs:
            job.cancel.set()
        for window in list(self.windows):
            window.close()
        if self.jobs or any(getattr(w, 'worker', None) and w.worker.isRunning() for w in self.windows):
            QTimer.singleShot(100, self.quit)
            return
        self.close()
        self.app.quit()

    def close(self):
        self.native.close()
        self.pointer_timer.stop()
        self.server.close()
        self.tray.hide()
        self.wheel.hide()


def math_ceil(value, divisor):
    return (value + divisor - 1) // divisor


def launch(args):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Cítrica')
    app.setOrganizationName('GenissonEmilio')
    app.setWindowIcon(QIcon(str(ICON)))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    import os
    from logging.handlers import RotatingFileHandler
    log_dir = Path(os.environ.get('LOCALAPPDATA', config.config_dir().parent)) / 'Citrica/Logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / 'citrica.log', maxBytes=1024*1024, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger('citrica').addHandler(handler)
    def report_exception(kind, error, traceback):
        logging.getLogger('citrica').error('Falha na interface', exc_info=(kind, error, traceback))
        QMessageBox.warning(None, 'Cítrica · falha', str(error) + '\nUse as configurações para salvar um diagnóstico.')
    sys.excepthook = report_exception
    if args.quit:
        result = send({'op': 'quit'})
        if not result:
            return 0
        import time
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if send({'op': 'status'}, timeout=100) is None:
                return 0
            QThread.msleep(100)
        return 1
    payload = ({'op': 'show', 'paths': [str(p.resolve()) for p in args.files]} if args.files or args.wheel or args.dock
               else {'op': 'pick'} if args.pick else {'op': 'status'} if args.background else {'op': 'settings'})
    existing = send(payload)
    if existing is not None:
        return 1 if existing.get('error') else 0
    desktop = Desktop(app)
    app.aboutToQuit.connect(desktop.close)
    if payload['op'] != 'status':
        desktop.dispatch(payload)
    if args.screenshot:
        def capture():
            window = next((w for w in desktop.windows if isinstance(w, Settings)), None)
            if window:
                window.grab().save(str(args.screenshot))
            desktop.quit()
        QTimer.singleShot(600, capture)
    return app.exec()
