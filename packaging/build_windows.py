"""Build Windows x64 GUI/CLI payload, portable ZIP and per-user Inno installer.

Run on Windows with requirements.lock and Inno Setup installed. FFmpeg,
LibreOffice and Tesseract remain optional external system dependencies.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from citrica import __version__

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
OUT = ROOT / 'release'
OUT.mkdir(exist_ok=True)
TEMP = ROOT / 'build/windows-package'
TEMP.mkdir(parents=True, exist_ok=True)


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def build():
    if sys.platform != 'win32':
        raise RuntimeError('O pacote Windows deve ser compilado no Windows.')
    # Rasterize the project's own vector logo into an Explorer/tray icon.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    from PIL import Image
    app = QApplication.instance() or QApplication([])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / 'citrica/assets/citrica.svg')).render(painter)
    painter.end()
    image.save(str(TEMP / 'icon.png'))
    Image.open(TEMP / 'icon.png').save(TEMP / 'citrica.ico', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    app.processEvents()
    # One collection, two launchers: no console flash for the GUI, reliable
    # stdout/exit codes for CLI conversion, diagnostics and automated checks.
    spec = TEMP / 'citrica-windows.spec'
    spec.write_text(f'''
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
datas = [(r"{ROOT / 'citrica/assets'}", 'citrica/assets'), (r"{TEMP / 'citrica.ico'}", 'citrica/assets')]
binaries, hiddenimports = [], []
for package in ['pillow_heif', 'pymupdf', 'pdf2docx']:
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files('cv2')
datas += collect_data_files('docx')
for package in ['Pillow', 'pypdf', 'PyMuPDF', 'PySide6-Essentials', 'shiboken6',
                'zxing-cpp', 'numpy', 'opencv-python-headless', 'python-docx', 'pdf2docx',
                'fonttools', 'lxml', 'fire', 'termcolor', 'typing_extensions', 'pywin32']:
    datas += copy_metadata(package)
a = Analysis([r"{ROOT / 'packaging/entry.py'}"], pathex=[r"{ROOT}"],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Citrica', console=False,
          icon=r"{TEMP / 'citrica.ico'}")
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='citrica-cli', console=True,
          icon=r"{TEMP / 'citrica.ico'}")
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='Citrica')
''', encoding='utf-8')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', str(spec))
    payload = ROOT / 'dist/Citrica'
    for file in ['README.md', 'LICENSE', 'THIRD_PARTY.md', 'requirements.lock']:
        shutil.copy2(ROOT / file, payload / file)
    shutil.copytree(ROOT / 'licenses', payload / 'licenses', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs/WINDOWS.md', payload / 'TESTAR-NO-WINDOWS.md')
    cli = payload / 'citrica-cli.exe'
    run(cli, '--version')
    # Source imports are not used to perform any conversion in this smoke test.
    from smoke import verify
    verify(cli)
    doctor = run(cli, '--doctor', capture_output=True, text=True, encoding='utf-8')
    data = json.loads(doctor.stdout)
    data['validation'] = {'runner': 'Windows Server 2022 x64 / GitHub Actions',
                          'packaged_engine_smoke': True,
                          'explorer': 'see separate citrica-windows-explorer-*-validation.json reports'}
    (OUT / 'citrica-windows-validation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                                          encoding='utf-8')
    run(payload / 'Citrica.exe', '--settings', '--screenshot', str(OUT / 'citrica-windows-preview.png'),
        env=dict(os.environ, QT_QPA_PLATFORM='windows'))
    shutil.make_archive(str(OUT / f'citrica-{__version__}-windows-x86_64-portable'), 'zip',
                        root_dir=ROOT / 'dist', base_dir='Citrica')
    compiler = shutil.which('ISCC.exe')
    if not compiler:
        compiler = str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) /
                       'Inno Setup 6/ISCC.exe')
    run(compiler, f'/DAppVersion={__version__}', f'/O{OUT}', str(ROOT / 'packaging/windows.iss'))
    checksums = [f"{hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()}  {p.name}"
                 for p in sorted(OUT.iterdir()) if p.name != 'SHA256SUMS-windows.txt']
    (OUT / 'SHA256SUMS-windows.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
