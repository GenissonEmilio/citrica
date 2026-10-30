"""Resident Windows app, tray, preferences, IPC and asynchronous wheel actions."""
import json
import faulthandler
import logging
import os
import platform
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCursor, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSystemTrayIcon, QTabWidget,
    QVBoxLayout, QWidget,
)

from citrica import __version__
from citrica.appearance import WheelAppearancePicker
from citrica.companion import Shelf, ToolDialog, file_action
from citrica.core import convert, dependencies
from citrica.desktop import request
from citrica.gui import ICON, STYLE
from citrica.windows import config, package
from citrica.windows.ipc import MAX_REQUEST, send, server_name
from citrica.windows.wheel import CENTER, SIZE, Wheel, hit_test

QA = logging.getLogger('citrica.qa')


@contextmanager
def qa_tracebacks(args):
    """Opt-in fatal crash capture and operation boundaries for desktop QA.

    Only a resident launched explicitly by the desktop harness enables this.
    No input paths or file contents are recorded by the boundary events.
    Never walk live frames from an asynchronous periodic watchdog: CPython3.12
    can crash in that diagnostic itself while Qt/Python threads change frames.
    """
    destination = os.environ.get('CITRICA_QA_TRACEBACK_LOG')
    if not destination or not args.background:
        yield
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path.with_suffix('.events.log'), encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(threadName)s %(message)s'))
    previous_level, previous_propagate = QA.level, QA.propagate
    QA.setLevel(logging.DEBUG)
    QA.propagate = False
    QA.addHandler(handler)
    try:
        with path.open('ab', buffering=0) as traces:
            fatal_was_enabled = faulthandler.is_enabled()
            try:
                # Preserve an existing fatal handler and its destination. A
                # frozen GUI normally has none; capture native crashes there.
                if not fatal_was_enabled:
                    faulthandler.enable(file=traces, all_threads=True)
                QA.debug('resident.qa_fatal_capture start pid=%s', os.getpid())
                yield
            finally:
                if not fatal_was_enabled:
                    faulthandler.disable()
                QA.debug('resident.qa_fatal_capture stop')
    finally:
        QA.removeHandler(handler)
        QA.setLevel(previous_level)
        QA.propagate = previous_propagate
        handler.close()


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
        self.resize(590, 700)
        layout = QVBoxLayout(self)
        title = QLabel('Cítrica · direto no seu arquivo')
        title.setStyleSheet('font-size:23px;font-weight:bold;')
        layout.addWidget(title)
        note = QLabel('Arraste um arquivo no Explorer e pressione Shift.\n'
                      'Alt: ferramentas · Ctrl: ações · Esc: cancelar.')
        note.setWordWrap(True)
        self.status = QLabel('O Cítrica continua na bandeja ao fechar esta janela.')
        if getattr(desktop.native, 'elevated', False):
            self.status.setText('Executando como administrador: o Windows pode bloquear arrastes do Explorer. '
                                'Feche pela bandeja e abra o Cítrica com permissões normais.')
        self.status.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('SettingsTabs')
        general = QWidget()
        general_layout = QVBoxLayout(general)
        general_layout.addWidget(note)
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
        general_layout.addLayout(form)
        self.tabs.addTab(general, 'Geral e atalhos')
        self.appearance = WheelAppearancePicker(desktop.settings.get('wheel_theme', 'classic'))
        appearance_scroll = QScrollArea()
        appearance_scroll.setWidgetResizable(True)
        appearance_scroll.setWidget(self.appearance)
        self.tabs.addTab(appearance_scroll, 'Personalizar a roda')
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        save = QPushButton('Salvar preferências')
        save.setObjectName('SavePreferences')
        save.clicked.connect(self.save)
        test = QPushButton('Salvar e testar roda')
        test.setObjectName('SaveAndTestWheel')
        test.clicked.connect(self.test)
        row.addWidget(save)
        row.addWidget(test)
        layout.addLayout(row)
        diagnostics = QPushButton('Salvar diagnóstico para suporte')
        diagnostics.clicked.connect(self.diagnostics)
        general_layout.addWidget(diagnostics)
        info = dependencies()
        details = QLabel('Processamento local · originais preservados.\n'
                         f"FFmpeg: {'disponível' if info['ffmpeg'] else 'não encontrado'} · "
                         f"LibreOffice: {'disponível' if info['libreoffice'] else 'opcional, não encontrado'}")
        details.setWordWrap(True)
        general_layout.addWidget(details)
        general_layout.addStretch()

    def save(self):
        try:
            self.desktop.apply_settings({'shortcut': self.shortcut.text().strip(),
                'drag_key': self.modifier.currentText(), 'animations': self.animations.isChecked(),
                'wheel_theme': self.appearance.theme_id()})
            if sys.platform == 'win32':
                config.set_startup(self.startup.isChecked())
            self.status.setText('Preferências salvas. O atalho e a tecla de arraste já estão ativos.')
            return True
        except Exception as error:
            QMessageBox.warning(self, 'Verifique as preferências', str(error))
            return False

    def test(self):
        if not self.save():
            return
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
        self.armed = False
        self.drag_epoch, self.drag_candidates, self.drag_verified = 0, [], False
        self.pending_drop = None
        self.offer_formats = []
        self.preview_error = ''
        self.jobs, self.windows = set(), set()
        self.counts = {'converted': 0, 'errors': 0}
        self.last_message, self.hotkey_error = '', ''
        self._quitting = False
        self.wheel = Wheel(lambda: self.settings['animations'])
        self.wheel.set_theme(self.settings.get('wheel_theme', 'classic'))
        self.wheel.filesOffered.connect(self.offer)
        self.wheel.dropped.connect(self.drop)
        self.wheel.offerObserved.connect(self.observe_offer)
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
        if hasattr(self.native, 'dragStarted'):
            self.native.dragStarted.connect(self.prepare_drag)
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
        self.pointer_timer.timeout.connect(self.poll_pointer)
        self.drag_release_timer = QTimer(self)
        self.drag_release_timer.setSingleShot(True)
        self.drag_release_timer.timeout.connect(self.finish_release)
        self._released_epoch = None
        self.pointer_timer.start(20)

    def _accept(self):
        QA.debug('ipc.accept')
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
                payload = json.loads(buffer.split(b'\n', 1)[0])
                QA.debug('ipc.dispatch begin op=%s', payload.get('op'))
                result = self.dispatch(payload)
                QA.debug('ipc.dispatch end')
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
        return {'platform': 'windows', 'version': __version__, 'visible': self.active, 'armed': self.armed,
                'origin': [self.wheel.x(), self.wheel.y()],
                'paths': [str(p) for p in self.paths], 'items': self.wheel.items,
                'selection': self.wheel.info, 'selected': self.wheel.selected,
                'cachedSelection': self.palette is not None, 'dragging': self.dragging,
                'busy': self.busy, 'mode': self.mode, 'counts': dict(self.counts),
                'offer_verified': self.drag_verified, 'offer_formats': self.offer_formats,
                'elevated': getattr(self.native, 'elevated', False),
                'preview_error': self.preview_error,
                'shortcut': self.settings['shortcut'], 'hotkey_active': not bool(self.hotkey_error),
                'hotkey_error': self.hotkey_error, 'last_message': self.last_message}

    def job(self, operation, done, failed=None):
        job = Job(operation)
        job.on_done = done
        job.on_failed = failed or (lambda error: self.notify('Cítrica · falha', error))
        self.jobs.add(job)
        job.result.connect(self._job_result)
        job.failed.connect(self._job_error)
        job.finished.connect(self._job_finished)
        job.start()

    @Slot(object)
    def _job_result(self, result):
        self.sender().on_done(result)

    @Slot(str)
    def _job_error(self, error):
        self.sender().on_failed(error)

    @Slot()
    def _job_finished(self):
        QA.debug('job.finished begin')
        job = self.sender()
        self.jobs.discard(job)
        job.deleteLater()
        QA.debug('job.finished deleteLater queued')

    def notify(self, title, message):
        self.last_message = message
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)

    def toggle(self):
        if self.active or self.armed:
            self.hide_wheel()
        else:
            self.show_wheel([])

    def show_wheel(self, paths, mode='convert', dragging=False, verified=True):
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
        self.drag_verified = verified
        if not self.active:
            cursor = QCursor.pos()
            screen = self.app.screenAt(cursor) or self.app.primaryScreen()
            rect = screen.availableGeometry()
            position = QPoint(max(rect.left(), min(cursor.x()-CENTER, rect.right()-SIZE+1)),
                              max(rect.top(), min(cursor.y()-CENTER, rect.bottom()-SIZE-35)))
            self.wheel.present(self.wheel.pos() if self.armed else position)
        self.armed = False
        self.active = self.native.visible = True
        if self.palette:
            self.render()
        elif paths:
            self.load_palette()

    def load_palette(self):
        token, paths = self.generation, list(self.paths)
        QA.debug('palette.begin generation=%s files=%s', token, len(paths))
        def done(palette):
            QA.debug('palette.done generation=%s current=%s active=%s', token, self.generation, self.active)
            if token != self.generation or not self.active:
                return
            self.palette = palette
            self.render()
        def failed(error):
            QA.debug('palette.failed generation=%s', token)
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
        if self.pending_drop and self.pending_drop[0] == self.generation:
            _token, point = self.pending_drop
            self.pending_drop = None
            selected = hit_test(point.x(), point.y(), len(current))
            if selected >= 0:
                self.apply(current[selected])
            else:
                self.hide_wheel()

    def observe_offer(self, formats):
        self.offer_formats = [str(f)[:200] for f in formats[:64]]

    def prepare_drag(self, hwnd):
        self.drag_epoch += 1
        epoch = self.drag_epoch
        QA.debug('preview.begin epoch=%s hwnd=%s', epoch, hwnd)
        self.drag_candidates = []
        self.preview_error = ''
        from citrica.windows.explorer import preview_files
        def done(paths):
            QA.debug('preview.done epoch=%s current=%s files=%s', epoch, self.drag_epoch, len(paths))
            if epoch != self.drag_epoch or not self.native.left_down():
                return
            self.drag_candidates = paths
            if paths and self.armed:
                self.show_wheel(paths, self.mode, dragging=True, verified=False)
        def failed(error):
            QA.debug('preview.failed epoch=%s', epoch)
            if epoch == self.drag_epoch:
                self.preview_error = error
            logging.getLogger('citrica').info('Prévia Explorer indisponível: %s', error)
        self.job(lambda _cancel: preview_files(hwnd), done, failed)

    def offer(self, paths):
        if paths != self.paths or not self.active:
            self.show_wheel(paths, self.mode, dragging=True)
        else:
            self.dragging = True
        self.drag_verified = True

    def drop(self, paths, point):
        QA.debug('drop.begin generation=%s files=%s', self.generation, len(paths))
        self.offer(paths)  # An actual OLE drop always supersedes a selection preview.
        self.dragging = False
        self.pending_drop = (self.generation, point)
        if self.palette:
            self.render()
        QA.debug('drop.end generation=%s', self.generation)

    def drag_mode(self, mode):
        QA.debug('drag_mode.begin mode=%s active=%s armed=%s', mode, self.active, self.armed)
        if self.active and not self.dragging and self.native.left_down():
            # A wheel left open by More or the global shortcut is not the new
            # physical drag. Discard that selection before probing this gesture;
            # prepare_drag already owns any pending Explorer preview for it.
            self.active = self.armed = False
            self.pending_drop = None
            self.drag_release_timer.stop()
        if not self.active:
            if self.busy or self._quitting:
                return
            self.mode = mode
            if not self.armed:
                self.generation += 1
                self.paths, self.palette = [], None
                self.wheel.clear()
            if not self.armed or self.wheel.probing:
                cursor = QCursor.pos()
                screen = self.app.screenAt(cursor) or self.app.primaryScreen()
                rect = screen.availableGeometry()
                position = QPoint(max(rect.left(), min(cursor.x()-CENTER, rect.right()-SIZE+1)),
                                  max(rect.top(), min(cursor.y()-CENTER, rect.bottom()-SIZE-35)))
                # Only reveal the ring once Qt receives a real local-file OLE
                # offer. Text selection and moving windows stay invisible.
                self.wheel.present(position, probing=True)
                self.armed = self.dragging = self.native.visible = True
            if self.drag_candidates:
                self.show_wheel(self.drag_candidates, mode, dragging=True, verified=False)
        elif mode != self.mode:
            self.mode, self.page = mode, 0
            self.render()
        QA.debug('drag_mode.end mode=%s active=%s armed=%s', self.mode, self.active, self.armed)

    def release(self):
        if not (self.dragging or self.armed) or self.drag_release_timer.isActive():
            return
        self._released_epoch = self.drag_epoch
        # OLE may dispatch Drop just after the physical button-up. Let its
        # validated file offer commit first. A late offer changes the palette
        # generation, but must not cancel dismissal of this physical drag.
        self.drag_release_timer.start(250)

    def finish_release(self):
        if (self._released_epoch == self.drag_epoch and (self.dragging or self.armed)
                and not self.native.left_down()):
            self.hide_wheel()

    def poll_pointer(self):
        if self.active:
            self.wheel.pointer(QCursor.pos())
        if self.dragging or self.armed:
            # Explorer's native OLE loop can consume the button-up notification.
            # Check its real state as well, without closing manually opened wheels
            # or a committed drop that is waiting for asynchronous file analysis.
            if self.native.left_down():
                self.drag_release_timer.stop()
            else:
                self.release()

    def hide_wheel(self):
        QA.debug('hide.begin generation=%s', self.generation)
        self.drag_release_timer.stop()
        self.generation += 1
        self.paths, self.palette, self.dragging, self.active = [], None, False, False
        self.armed = False
        self.drag_epoch += 1
        self.drag_candidates, self.drag_verified, self.pending_drop = [], False, None
        self.page = 0
        self.native.visible = False
        self.native.reset_drag()
        self.wheel.dismiss()
        QA.debug('hide.end generation=%s', self.generation)

    def apply(self, item):
        if self.dragging and not self.drag_verified:
            self.notify('Cítrica', 'Mova o arquivo sobre a opção e solte para confirmar o arraste.')
            return
        if item['kind'] == 'page':
            # Dropping on More ends OLE, but keeps this selection available for
            # the next click. A subsequent fresh opening still clears it.
            self.dragging = False
            self.native.reset_drag()
            self.page = int(item['id'])
            self.render()
            return
        paths = list(self.paths)
        self.hide_wheel()
        if not paths:
            return
        if item['kind'] == 'tool':
            # Return to OLE before touching the clipboard or opening a dialog.
            # Explorer can still own its data object while Drop is on our stack.
            def action():
                if self._quitting:
                    return
                try:
                    if item['id'] == 'float':
                        self.keep_window(Shelf(paths))
                    elif item['id'] in {'copy', 'copy_path', 'terminal', 'move', 'share'}:
                        file_action(item['id'], paths, resident=True)
                    else:
                        self.keep_window(ToolDialog(item['id'], paths))
                except Exception as error:
                    self.notify('Cítrica · falha', str(error))
            QTimer.singleShot(0, action)
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
        self.wheel.set_theme(self.settings.get('wheel_theme', 'classic'))
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
        self.drag_release_timer.stop()
        self.server.close()
        self.tray.hide()
        self.wheel.hide()


def math_ceil(value, divisor):
    return (value + divisor - 1) // divisor


def launch(args):
    with qa_tracebacks(args):
        return _launch(args)


def _launch(args):
    if args.quit:
        from citrica.windows.ipc import quit_resident
        return quit_resident()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Cítrica')
    app.setOrganizationName('GenissonEmilio')
    app.setWindowIcon(QIcon(str(ICON)))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    from logging.handlers import RotatingFileHandler
    log_dir = (package.application_paths()['local_cache'] / 'Citrica/Logs' if package.package_family_name()
               else Path(os.environ.get('LOCALAPPDATA', config.config_dir().parent)) / 'Citrica/Logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / 'citrica.log', maxBytes=1024*1024, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger('citrica').addHandler(handler)
    logging.getLogger('citrica').setLevel(logging.INFO)
    def report_exception(kind, error, traceback):
        logging.getLogger('citrica').error('Falha na interface', exc_info=(kind, error, traceback))
        QMessageBox.warning(None, 'Cítrica · falha', str(error) + '\nUse as configurações para salvar um diagnóstico.')
    sys.excepthook = report_exception
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
