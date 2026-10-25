"""Qt desktop shell: a keyboard-accessible wheel, batch queue, and floating drop target."""

from __future__ import annotations

import math
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from citrica import __version__
from citrica.core import LABELS, Options, batch, common_formats, dependencies, family, merge_pdfs

ICON = Path(__file__).parent / "assets" / "citrica.svg"
if sys.platform == 'win32' and ICON.with_suffix('.ico').is_file():
    ICON = ICON.with_suffix('.ico')
ORANGE = "#ed713d"

STYLE = """
QWidget { background: #f8f7f3; color: #282e2a; font-family: 'Noto Sans', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #f8f7f3; }
QLabel { background: transparent; }
QLabel#brand { font-size: 25px; font-weight: 700; letter-spacing: -1px; }
QLabel#hero { font-size: 29px; font-weight: 700; letter-spacing: -1px; }
QLabel#muted { color: #7d827b; }
QLabel#eyebrow { color: #8a9084; font-size: 10px; letter-spacing: 2px; font-weight: 600; }
QFrame#sidebar { background: #eeeee7; border: none; border-right: 1px solid #e3e4dc; }
QFrame#sidebar QLabel { background: transparent; }
QFrame#card { border: 1px solid #e3e4dc; border-radius: 14px; background: #fffefa; }
QFrame#card QWidget { background: transparent; }
QPushButton { background: #fffefa; border: 1px solid #dedfd6; border-radius: 9px; padding: 10px 16px; }
QPushButton:hover { background: #f1f0e7; border-color: #bfc4b6; }
QPushButton:focus { border: 2px solid #ed713d; }
QPushButton:disabled { color: #a1a49a; background: #efefe8; }
QPushButton#primary { background: #ed713d; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #d96031; }
QPushButton#primary:disabled { background: #d7c9bb; }
QPushButton#nav { background: #e1e6d5; text-align: left; border: none; color: #3c4c34; font-weight: 600; }
QPushButton#subtle { background: transparent; border: none; color: #79816f; text-align: left; padding-left: 0; }
QListWidget { background: #fffefa; border: 1px solid #e3e4dc; border-radius: 12px; padding: 8px; }
QListWidget::item { padding: 10px 8px; border-bottom: 1px solid #f0f0e8; }
QListWidget::item:selected { background: #fbe9de; color: #282e2a; border-radius: 6px; }
QComboBox, QSpinBox { background: #fffefa; border: 1px solid #dedfd6; border-radius: 7px; padding: 7px; }
QCheckBox { spacing: 8px; }
QSlider::groove:horizontal { height: 5px; background: #e3e4dc; border-radius: 2px; }
QSlider::handle:horizontal { background: #ed713d; width: 15px; margin: -5px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #ed713d; border-radius: 2px; }
QProgressBar { border: none; border-radius: 4px; background: #e3e4dc; height: 7px; text-align: center; }
QProgressBar::chunk { background: #90a875; border-radius: 4px; }
QToolTip { color: #282e2a; background: #fffefa; border: 1px solid #dedfd6; padding: 5px; }
"""
if sys.platform == 'win32':
    STYLE = STYLE.replace("font-family: 'Noto Sans', 'DejaVu Sans';", "font-family: 'Segoe UI';")


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(False)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    widget.setMinimumHeight(38)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def paths_from_mime(mime) -> list[Path]:
    return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile() and Path(url.toLocalFile()).is_file()]


class Wheel(QWidget):
    chosen = Signal(str)
    files_dropped = Signal(list, str)
    browse = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(350, 350)
        self.setAcceptDrops(True)
        self.formats = []
        self.caption = "SOLTE SEUS ARQUIVOS"
        self.preview = False
        self.buttons = []
        self.center = button("+", self.browse.emit)
        self.center.setParent(self)
        self.center.setStyleSheet("QPushButton {background:#ed713d;color:#fff6dc;border:none;"
                                 "border-radius:38px;font-size:33px;} QPushButton:hover {background:#d96031;}")
        self.center.setAccessibleName("Escolher arquivos")
        self.dragging = False

    def set_formats(self, choices, caption="ESCOLHA UM FORMATO", preview=False):
        for widget in self.buttons:
            widget.deleteLater()
        self.formats, self.caption, self.preview = choices, caption, preview
        self.buttons = []
        for fmt in choices:
            widget = button(fmt.upper(), lambda _=False, fmt=fmt: self.chosen.emit(fmt))
            widget.setParent(self)
            widget.setAccessibleName(f"Converter para {fmt.upper()}")
            widget.setToolTip(f"Converter para {fmt.upper()}" if not preview else "Adicione arquivos para começar")
            widget.setEnabled(not preview)
            widget.show()
            self.buttons.append(widget)
        self._position()
        self.update()

    def _position(self):
        cx, cy = self.width() / 2, self.height() / 2 - 9
        self.center.setGeometry(int(cx - 38), int(cy - 38), 76, 76)
        radius = min(self.width(), self.height()) * 0.34
        for i, widget in enumerate(self.buttons):
            angle = -math.pi / 2 + 2 * math.pi * i / len(self.buttons)
            widget.setGeometry(int(cx + radius * math.cos(angle) - 39),
                               int(cy + radius * math.sin(angle) - 20), 78, 40)

    def resizeEvent(self, event):
        self._position()
        super().resizeEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2 - 9
        radius = min(self.width(), self.height()) * 0.34
        painter.setBrush(QColor("#f1f2e9" if not self.dragging else "#fae5d8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - radius - 25, cy - radius - 25, 2 * radius + 50, 2 * radius + 50))
        painter.setPen(QPen(QColor("#dce1d1"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - radius + 4, cy - radius + 4, 2 * radius - 8, 2 * radius - 8))
        painter.setPen(QColor("#8b927f"))
        font = QFont(self.font())
        font.setPixelSize(9)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        painter.setFont(font)
        painter.drawText(QRectF(cx - 140, cy + 47, 280, 20), Qt.AlignmentFlag.AlignCenter, self.caption)

    def dragEnterEvent(self, event):
        paths = paths_from_mime(event.mimeData())
        if paths:
            self.set_formats(common_formats(paths), "SOLTE NO FORMATO")
            self.dragging = True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.update()

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.dragging = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        paths = paths_from_mime(event.mimeData())
        chosen = ""
        point = event.position().toPoint()
        for fmt, widget in zip(self.formats, self.buttons):
            if widget.geometry().contains(point):
                chosen = fmt
        self.dragging = False
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.files_dropped.emit(paths, chosen)
        self.update()


class Worker(QThread):
    item_done = Signal(object, list, str)

    def __init__(self, paths, fmt, output, opts, merge=False):
        super().__init__()
        self.paths, self.fmt, self.output, self.opts, self.merge = paths, fmt, output, opts, merge
        self.cancel = threading.Event()

    def run(self):
        if self.merge:
            try:
                result = merge_pdfs(self.paths, self.output, self.cancel)
                self.item_done.emit(self.paths[0], result, "")
            except Exception as error:
                self.item_done.emit(self.paths[0], [], str(error))
        else:
            batch(self.paths, self.fmt, self.output, self.opts, self.cancel,
                  lambda source, result, error: self.item_done.emit(source, result, error))


class DropDock(QWidget):
    def __init__(self, window):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.window = window
        self.setWindowTitle("Cítrica · área flutuante")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(388, 434)
        self.setMinimumSize(388, 434)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(label("Cítrica", "brand"))
        header.addStretch()
        header.addWidget(button("Abrir", self.open_main))
        layout.addLayout(header)
        self.wheel = Wheel()
        self.wheel.set_formats(["png", "jpg", "webp", "pdf", "mp3", "mp4"], preview=True)
        self.wheel.files_dropped.connect(self.dropped)
        self.wheel.chosen.connect(window.start_conversion)
        self.wheel.browse.connect(window.browse)
        layout.addWidget(self.wheel)
        layout.addWidget(label("Arraste um arquivo e solte no formato desejado.", "muted"))

    def open_main(self):
        self.window.show()
        self.window.raise_()
        self.hide()

    def dropped(self, paths, fmt):
        self.window.set_files(paths)
        if fmt:
            self.window.start_conversion(fmt)
            self.window.show()
        self.wheel.set_formats(common_formats(paths))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.paths, self.outputs = [], []
        self.worker = None
        self.output_dir = None
        self.dock = None
        self.completed = self.failed = 0
        self.setWindowTitle("Cítrica · conversor de arquivos")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1120, 900)
        self.setMinimumSize(1020, 860)
        self.setAcceptDrops(True)
        root = QWidget()
        self.setCentralWidget(root)
        horizontal = QHBoxLayout(root)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(226)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(24, 29, 24, 22)
        side.setSpacing(17)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICON)).pixmap(37, 37))
        brand.addWidget(logo)
        brand.addWidget(label("cítrica", "brand"))
        brand.addStretch()
        side.addLayout(brand)
        side.addWidget(label("CONVERSÃO SEM DESVIOS", "eyebrow"))
        side.addSpacing(22)
        side.addWidget(button("◉   Converter arquivos", lambda: None, "nav"))
        side.addWidget(button("⊕   Área flutuante", self.show_dock, "subtle"))
        side.addWidget(button("↗   Integração com Linux", self.show_integration, "subtle"))
        side.addStretch()
        side.addWidget(label("FEITO PARA O SEU LINUX", "eyebrow"))
        side.addWidget(label("●  Processamento local\n●  Sem conta ou limite\n●  Originais preservados", "muted"))
        side.addSpacing(14)
        side.addWidget(button("Sobre o Cítrica", self.about, "subtle"))
        side.addWidget(label(f"v{__version__}  /  código aberto", "muted"))
        horizontal.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(35, 28, 35, 22)
        main.setSpacing(14)
        horizontal.addLayout(main, 1)
        top = QHBoxLayout()
        top.addWidget(label("CONVERSOR LOCAL", "eyebrow"))
        top.addStretch()
        top.addWidget(label("●  100% offline", "muted"))
        main.addLayout(top)
        main.addWidget(label("Novo formato. Mesmo fluxo.", "hero"))
        main.addWidget(label("Arraste, escolha e pronto. A cópia fica ao lado do original.", "muted"))
        content = QHBoxLayout()
        content.setSpacing(20)
        self.wheel = Wheel()
        self.wheel.set_formats(["png", "jpg", "webp", "pdf", "mp3", "mp4"], preview=True)
        self.wheel.chosen.connect(self.start_conversion)
        self.wheel.files_dropped.connect(self.dropped)
        self.wheel.browse.connect(self.browse)
        content.addWidget(self.wheel, 1)
        panel = QVBoxLayout()
        panel.setSpacing(12)
        panel.addWidget(label("01  ADICIONE SEUS ARQUIVOS", "eyebrow"))
        self.selection = label("Tudo começa com um arquivo.")
        self.selection.setWordWrap(True)
        panel.addWidget(self.selection)
        panel.addWidget(button("+  Escolher arquivos", self.browse, "primary"))
        self.clear_button = button("Limpar seleção", self.clear_files)
        panel.addWidget(self.clear_button)
        panel.addSpacing(8)
        panel.addWidget(label("02  FORMATO DE SAÍDA", "eyebrow"))
        self.format_combo = QComboBox()
        self.format_combo.setAccessibleName("Formato de saída")
        panel.addWidget(self.format_combo)
        self.convert_button = button("Converter arquivos  →", lambda: self.start_conversion(), "primary")
        self.convert_button.setEnabled(False)
        panel.addWidget(self.convert_button)
        self.merge_button = button("Unir PDFs selecionados", lambda: self.start_conversion(merge=True))
        self.merge_button.setVisible(False)
        panel.addWidget(self.merge_button)
        panel.addStretch()
        panel.addWidget(label("Imagens · PDF · vídeo · áudio\nDocumentos · legendas · arquivos", "muted"))
        content.addLayout(panel, 1)
        main.addLayout(content)
        options = QFrame()
        options.setObjectName("card")
        opts = QVBoxLayout(options)
        opts.setContentsMargins(16, 12, 16, 12)
        row = QHBoxLayout()
        row.addWidget(label("Qualidade"))
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(1, 100)
        self.quality.setValue(85)
        self.quality.setAccessibleName("Qualidade da imagem ou vídeo")
        row.addWidget(self.quality)
        self.quality_label = label("85%")
        self.quality.valueChanged.connect(lambda v: self.quality_label.setText(f"{v}%"))
        row.addWidget(self.quality_label)
        row.addSpacing(18)
        row.addWidget(label("Largura máx."))
        self.width_box = QSpinBox()
        self.width_box.setRange(0, 16384)
        self.width_box.setSingleStep(100)
        self.width_box.setSpecialValueText("Original")
        self.width_box.setSuffix(" px")
        self.width_box.setAccessibleName("Largura máxima em pixels, zero mantém original")
        row.addWidget(self.width_box)
        opts.addLayout(row)
        row2 = QHBoxLayout()
        self.strip = QCheckBox("Remover metadados")
        self.strip.setToolTip("Imagens, PDF e mídia. Documentos Office mantêm metadados do LibreOffice.")
        self.strip.setChecked(True)
        row2.addWidget(self.strip)
        row2.addStretch()
        self.destination = button("Salvar: junto ao original  ▾", self.choose_output, "subtle")
        row2.addWidget(self.destination)
        opts.addLayout(row2)
        main.addWidget(options)
        queue_header = QHBoxLayout()
        queue_header.addWidget(label("NESTA SESSÃO", "eyebrow"))
        queue_header.addStretch()
        self.reveal_button = button("Abrir pasta de saída ↗", self.reveal, "subtle")
        self.reveal_button.setEnabled(False)
        queue_header.addWidget(self.reveal_button)
        main.addLayout(queue_header)
        self.queue = QListWidget()
        self.queue.setMinimumHeight(90)
        self.queue.setMaximumHeight(145)
        self.queue.setAccessibleName("Arquivos selecionados e resultados")
        self.queue.itemDoubleClicked.connect(self.open_item)
        empty = QListWidgetItem("As conversões desta sessão aparecem aqui.")
        empty.setFlags(Qt.ItemFlag.NoItemFlags)
        self.queue.addItem(empty)
        main.addWidget(self.queue, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        main.addWidget(self.progress)
        footer = QHBoxLayout()
        self.status = label(self.dependency_text(), "muted")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer.addWidget(self.status, 1)
        self.cancel_button = button("Cancelar", self.cancel)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        main.addLayout(footer)
        QShortcut(QKeySequence.StandardKey.Open, self, self.browse)
        QShortcut(QKeySequence("Escape"), self, self.cancel)
        QShortcut(QKeySequence("Ctrl+Return"), self, lambda: self.start_conversion())
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(str(ICON)), self)
            self.tray.setToolTip("Cítrica · conversão local")
            menu = QMenu()
            menu.addAction("Abrir Cítrica", self.show)
            menu.addAction("Área flutuante", self.show_dock)
            menu.addAction("Sair", self.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda _reason: self.show())
            self.tray.show()

    @staticmethod
    def dependency_text():
        deps = dependencies()
        return "  ·  ".join(f"{name}: {'disponível' if path else 'não instalado'}" for name, path in deps.items())

    def browse(self):
        if self.worker and self.worker.isRunning():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Escolher arquivos para converter")
        if paths:
            self.set_files([Path(path) for path in paths])
            if self.dock and self.dock.isVisible():
                self.dock.wheel.set_formats(common_formats(self.paths))

    def dropped(self, paths, fmt):
        self.set_files(paths)
        if fmt:
            self.start_conversion(fmt)

    def set_files(self, paths):
        if self.worker and self.worker.isRunning():
            return
        self.paths = list(dict.fromkeys(Path(p).resolve() for p in paths if Path(p).is_file()))
        self.queue.clear()
        for path in self.paths:
            item = QListWidgetItem(f"○  {path.name}    ·    {LABELS[family(path)]}")
            item.setToolTip(str(path))
            self.queue.addItem(item)
        formats = common_formats(self.paths)
        self.format_combo.clear()
        self.format_combo.addItems([fmt.upper() for fmt in formats])
        self.wheel.set_formats(formats)
        self.convert_button.setEnabled(bool(formats))
        self.merge_button.setVisible(len(self.paths) > 1 and all(family(p) == "pdf" for p in self.paths))
        if self.paths:
            size = sum(path.stat().st_size for path in self.paths)
            title = self.paths[0].name if len(self.paths) == 1 else f"{len(self.paths)} arquivos selecionados"
            self.selection.setText(f"{title}\n{size / 1024**2:.2f} MB no total")
            self.status.setText("Escolha um formato no círculo ou na lista." if formats else
                                "Sem formato em comum. Verifique a seleção e as dependências.")
        else:
            self.selection.setText("Tudo começa com um arquivo.")
            self.wheel.set_formats(["png", "jpg", "webp", "pdf", "mp3", "mp4"], preview=True)
            self.status.setText(self.dependency_text())

    def clear_files(self):
        self.set_files([])

    def choose_output(self):
        menu = QMenu(self)
        menu.addAction("Junto ao original", lambda: self.set_output(None))
        menu.addAction("Escolher outra pasta…", self.pick_output)
        menu.exec(self.destination.mapToGlobal(QPoint(0, self.destination.height())))

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Salvar cópias em")
        if folder:
            self.set_output(Path(folder))

    def set_output(self, path):
        self.output_dir = path
        self.destination.setText(f"Salvar: {path.name if path else 'junto ao original'}  ▾")
        self.destination.setToolTip(str(path) if path else "Uma cópia na pasta de cada arquivo original")

    def start_conversion(self, fmt=None, merge=False):
        if not self.paths or (self.worker and self.worker.isRunning()):
            return
        fmt = (fmt or self.format_combo.currentText()).lower()
        if not merge and fmt not in common_formats(self.paths):
            return
        opts = Options(self.quality.value(), self.width_box.value(), self.strip.isChecked())
        self.worker = Worker(self.paths.copy(), fmt, self.output_dir, opts, merge)
        self.worker.item_done.connect(self.result)
        self.worker.finished.connect(self.finished)
        self.completed = self.failed = 0
        self.progress.setRange(0, 1 if merge else len(self.paths))
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()
        self.convert_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.merge_button.setEnabled(False)
        self.status.setText("Convertendo localmente…")
        self.worker.start()

    def result(self, source, outputs, error):
        self.completed += 1
        self.progress.setValue(self.completed)
        if error:
            self.failed += 1
            item = QListWidgetItem(f"!  {source.name}  ·  {error[:150]}")
            item.setToolTip(error)
            item.setForeground(QColor("#b74732"))
            self.queue.addItem(item)
        else:
            for output in outputs:
                self.outputs.append(output)
                item = QListWidgetItem(f"✓  {output.name}    ·    {output.stat().st_size / 1024:.1f} KB")
                item.setData(Qt.ItemDataRole.UserRole, str(output))
                item.setToolTip(f"{output}\nDuplo clique para abrir")
                item.setForeground(QColor("#577443"))
                self.queue.addItem(item)
            self.reveal_button.setEnabled(True)
        self.queue.scrollToBottom()

    def finished(self):
        cancelled = self.worker.cancel.is_set()
        self.status.setText("Cancelado. As cópias já concluídas foram mantidas." if cancelled else
                            f"Concluído: {self.completed - self.failed} operação(ões), {self.failed} falha(s).")
        self.convert_button.setEnabled(bool(common_formats(self.paths)))
        self.clear_button.setEnabled(True)
        self.merge_button.setEnabled(True)
        self.cancel_button.hide()
        if self.tray and not self.isVisible():
            self.tray.showMessage("Cítrica", self.status.text())

    def cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.status.setText("Cancelando a operação…")

    def reveal(self):
        if self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.outputs[-1].parent)))

    def open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_dock(self):
        if self.dock is None:
            self.dock = DropDock(self)
        self.dock.show()
        self.dock.raise_()

    def show_integration(self):
        QMessageBox.information(self, "Cítrica no seu Linux",
                                "Use a área flutuante para arrastar arquivos de qualquer gerenciador.\n\n"
                                "Instale os menus de contexto com:\n"
                                "citrica --install-integrations\n\n"
                                "Nautilus, Nemo e Dolphin são suportados. Reinicie o gerenciador após instalar.\n\n"
                                "Você também pode associar um atalho do sistema a: citrica --dock\n\n"
                                "O Shift global do macOS não é interceptado no Wayland. "
                                "Nenhuma permissão de captura do teclado é solicitada.")

    def about(self):
        QMessageBox.about(self, "Sobre o Cítrica", f"Cítrica {__version__}\n\n"
                          "Um conversor de arquivos para Linux, local, gratuito e de código aberto.\n"
                          "Criado por GenissonEmilio. Licença AGPL-3.0-or-later.\n\n"
                          "Inspirado na interação do Tangerine, com código e identidade próprios.\n"
                          "github.com/GenissonEmilio/citrica\n\n" + self.dependency_text())

    def dragEnterEvent(self, event):
        if paths_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

    def dropEvent(self, event):
        self.set_files(paths_from_mime(event.mimeData()))
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel()
            self.status.setText("Cancelando antes de fechar…")
            event.ignore()
            self.worker.finished.connect(self.close)
            return
        if self.dock:
            self.dock.close()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()
        event.accept()


def launch(paths=None, dock=False, wheel=False, screenshot=None):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Cítrica")
    app.setDesktopFileName("io.github.GenissonEmilio.citrica")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    if paths:
        window.set_files(paths)
    if dock or wheel:
        window.show_dock()
        if paths:
            window.dock.wheel.set_formats(common_formats(window.paths))
    else:
        window.show()
    if screenshot:
        def capture():
            window.grab().save(str(screenshot))
            app.quit()
        QTimer.singleShot(600, capture)
    return app.exec()
