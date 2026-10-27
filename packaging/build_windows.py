"""Build Windows x64 GUI/CLI payload, portable ZIP and per-user Inno installer.

Run on Windows with requirements.lock, Inno Setup, and the offline engine tree
prepared by prepare_windows_engines.py. No engines are downloaded by the app.
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
    from sign_windows import SigningConfig, inno_signing_arguments, sign_files, verify_files
    signing = SigningConfig.from_environment()
    engines = Path(os.environ.get('CITRICA_WINDOWS_ENGINES', ROOT / 'build/windows-engines')).resolve()
    for relative in ['tools/ffmpeg/bin/ffmpeg.exe', 'tools/ffmpeg/bin/ffprobe.exe',
                     'tools/libreoffice/program/soffice.com', 'ocr/libtesseract-5.dll',
                     'ocr/tessdata/eng.traineddata', 'engines.json', 'engine-files.sha256.json']:
        if not (engines / relative).is_file():
            raise RuntimeError('Prepare os motores offline antes de compilar: '
                               'python packaging/prepare_windows_engines.py '
                               f'(arquivo ausente: {engines / relative})')
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
    version = tuple(map(int, __version__.split('.'))) + (0,)
    version_file = TEMP / 'version-info.txt'
    version_file.write_text(f'''VSVersionInfo(
ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Genisson Emilio'),
    StringStruct('FileDescription', 'Citrica - conversor de arquivos local'),
    StringStruct('FileVersion', {__version__!r}),
    StringStruct('ProductName', 'Citrica'),
    StringStruct('ProductVersion', {__version__!r}),
    StringStruct('LegalCopyright', 'Genisson Emilio - AGPL-3.0-or-later')
])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding='utf-8')
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
          icon=r"{TEMP / 'citrica.ico'}", version=r"{version_file}")
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='citrica-cli', console=True,
          icon=r"{TEMP / 'citrica.ico'}", version=r"{version_file}")
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='Citrica')
''', encoding='utf-8')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', str(spec))
    payload = ROOT / 'dist/Citrica'
    # These are independent executables with their complete library trees.
    # Copy after collection to avoid PyInstaller treating Office/FFmpeg DLLs as
    # application imports or mixing their DLLs with Qt's dependencies.
    shutil.copytree(engines, payload / '_internal', dirs_exist_ok=True)
    for file in ['README.md', 'LICENSE', 'THIRD_PARTY.md', 'requirements.lock']:
        shutil.copy2(ROOT / file, payload / file)
    shutil.copytree(ROOT / 'licenses', payload / 'licenses', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs/WINDOWS.md', payload / 'TESTAR-NO-WINDOWS.md')
    cli = payload / 'citrica-cli.exe'
    run(cli, '--version')
    # Source imports are not used to perform any conversion in this smoke test.
    from smoke import verify
    verify(cli)
    run(sys.executable, ROOT / 'tests/windows/engine_parity.py', cli)
    doctor = run(cli, '--doctor', capture_output=True, text=True, encoding='utf-8')
    data = json.loads(doctor.stdout)
    data['validation'] = {'runner': 'Windows Server 2022 x64 / GitHub Actions',
                          'packaged_engine_smoke': True,
                          'offline_engines': json.loads((engines / 'engines.json').read_text(encoding='utf-8')),
                          'conversion_matrix': 'citrica-windows-engine-parity.json',
                          'explorer': 'see separate citrica-windows-explorer-*-validation.json reports'}
    (OUT / 'citrica-windows-validation.json').write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                                          encoding='utf-8')
    run(payload / 'Citrica.exe', '--settings', '--screenshot', str(OUT / 'citrica-windows-preview.png'),
        env=dict(os.environ, QT_QPA_PLATFORM='windows'))
    trust = {'authenticode_verified': signing is not None,
             'scope': ['Citrica.exe', 'citrica-cli.exe', 'setup.exe', 'uninstaller.exe'] if signing else [],
             'smartscreen_reputation_verified': False,
             'files': sign_files(signing, [payload / 'Citrica.exe', cli]) if signing else [],
             'status': 'signed' if signing else 'unsigned'}
    # Only Cítrica's launchers are signed by our publisher. Upstream Office,
    # codec and OCR binaries retain their original signatures and hashes.
    shutil.make_archive(str(OUT / f'citrica-{__version__}-windows-x86_64-portable'), 'zip',
                        root_dir=ROOT / 'dist', base_dir='Citrica')
    compiler = shutil.which('ISCC.exe')
    if not compiler:
        compiler = str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) /
                       'Inno Setup 6/ISCC.exe')
    run(compiler, *(inno_signing_arguments(signing) if signing else []), f'/DAppVersion={__version__}', f'/O{OUT}',
        str(ROOT / 'packaging/windows.iss'))
    if signing:
        installer = OUT / f'citrica-{__version__}-windows-x86_64-setup.exe'
        trust['files'] += verify_files([installer], signtool=signing.signtool)
    (OUT / 'citrica-windows-signing.json').write_text(json.dumps(trust, indent=2, ensure_ascii=False) + '\n',
                                                  encoding='utf-8')
    checksums = [f"{hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()}  {p.name}"
                 for p in sorted(OUT.iterdir()) if p.name != 'SHA256SUMS-windows.txt']
    (OUT / 'SHA256SUMS-windows.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
