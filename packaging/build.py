"""Build portable and native Linux packages from the same dynamically linked payload."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from citrica import __version__
from smoke import verify
from linux_package import build_deb, glibc_floor

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
OUT = ROOT / "release"
OUT.mkdir(exist_ok=True)


def run(*args):
    subprocess.run(list(args), check=True)


ocr = []
for library in [Path('/usr/lib/x86_64-linux-gnu/libtesseract.so.5'), Path('/usr/lib64/libtesseract.so.5.5')]:
    if library.is_file():
        ocr += ['--add-binary', f'{library.resolve()}:.']
        break
for model in [Path('/usr/share/tesseract-ocr/5/tessdata/eng.traineddata'),
              Path('/usr/share/tesseract/tessdata/eng.traineddata')]:
    if model.is_file():
        ocr += ['--add-data', f'{model}:ocr-data']
        break

run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "citrica",
    "--onedir", "--add-data", "citrica/assets:citrica/assets", "--collect-all", "pillow_heif",
    "--add-data", "gnome:gnome",
    "--collect-data", "cv2", "--copy-metadata", "opencv-python-headless",
    "--collect-all", "pymupdf", "--copy-metadata", "Pillow", "--copy-metadata", "pypdf",
    "--collect-all", "pdf2docx", "--collect-data", "docx",
    "--copy-metadata", "python-docx", "--copy-metadata", "pdf2docx",
    "--copy-metadata", "fonttools", "--copy-metadata", "lxml",
    "--copy-metadata", "fire", "--copy-metadata", "termcolor", "--copy-metadata", "typing_extensions",
    "--copy-metadata", "PyMuPDF", "--copy-metadata", "PySide6-Essentials",
    "--copy-metadata", "PySide6-Addons",
    "--copy-metadata", "zxing-cpp", "--copy-metadata", "numpy",
    "--copy-metadata", "shiboken6", *ocr, "packaging/entry.py")

payload = ROOT / "dist/citrica"
for name in ["README.md", "LICENSE", "THIRD_PARTY.md"]:
    shutil.copy2(ROOT / name, payload / name)
shutil.copytree(ROOT / "licenses", payload / "licenses", dirs_exist_ok=True)
for package in ['libtesseract5', 'liblept5', 'tesseract-ocr-eng', 'libpulse0']:
    copyright_file = Path('/usr/share/doc') / package / 'copyright'
    if copyright_file.is_file():
        shutil.copy2(copyright_file, payload / 'licenses' / f'{package}-copyright.txt')
lgpl21 = Path('/usr/share/common-licenses/LGPL-2.1')
if lgpl21.is_file():
    shutil.copy2(lgpl21, payload / 'licenses' / 'LGPL-2.1.txt')
shutil.copy2(ROOT / "requirements.lock", payload / "requirements.lock")
shutil.copytree(ROOT / 'gnome', payload / 'gnome', dirs_exist_ok=True)
shutil.copy2(ROOT / "packaging/install.sh", payload / "install.sh")
(payload / "install.sh").chmod(0o755)
run(str(payload / "citrica"), "--doctor")
verify(payload / "citrica")
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
subprocess.run([str(payload / "citrica"), "--settings", "--screenshot", str(OUT / "citrica-preview.png")],
               env=env, check=True)
shutil.copy2(ROOT / 'docs/wheel.png', OUT / 'citrica-wheel.png')
run("tar", "-czf", str(OUT / f"citrica-{__version__}-linux-x86_64.tar.gz"), "-C", str(ROOT / "dist"), "citrica")

if shutil.which("dpkg-deb"):
    build_deb(ROOT, payload, OUT, __version__)

if shutil.which("rpmbuild"):
    top = ROOT / "build/rpm"
    for folder in ["BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS", "BUILDROOT"]:
        (top / folder).mkdir(parents=True, exist_ok=True)
    spec = top / "SPECS/citrica.spec"
    spec.write_text(f"""Name: citrica
Version: {__version__}
Release: 1
Summary: Conversor local de arquivos com menu radial
License: AGPL-3.0-or-later
URL: https://github.com/GenissonEmilio/citrica
AutoReqProv: no
Requires: glibc >= {glibc_floor()}
Requires: libglvnd-glx, libglvnd-egl, libxkbcommon, libxcb, xcb-util-cursor, fontconfig, dbus-libs
Requires: xcb-util-wm, xcb-util-keysyms, xcb-util-image, xcb-util-renderutil, libxkbcommon-x11
Recommends: ffmpeg, libreoffice, python3-gobject, gnome-shell, tesseract-libs, tesseract-langpack-eng
%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%description
Conversor offline de imagens, PDF, áudio, vídeo, documentos e legendas.
%install
mkdir -p %{{buildroot}}/opt %{{buildroot}}/usr/bin %{{buildroot}}/usr/share/applications %{{buildroot}}/usr/share/metainfo
cp -a "{payload}" %{{buildroot}}/opt/citrica
ln -s /opt/citrica/citrica %{{buildroot}}/usr/bin/citrica
cp "{ROOT}/packaging/io.github.GenissonEmilio.citrica.desktop" %{{buildroot}}/usr/share/applications/
cp "{ROOT}/packaging/io.github.GenissonEmilio.citrica.metainfo.xml" %{{buildroot}}/usr/share/metainfo/
mkdir -p %{{buildroot}}/usr/share/icons/hicolor/scalable/apps
cp "{ROOT}/citrica/assets/citrica.svg" %{{buildroot}}/usr/share/icons/hicolor/scalable/apps/io.github.GenissonEmilio.citrica.svg
%files
/opt/citrica
/usr/bin/citrica
/usr/share/applications/io.github.GenissonEmilio.citrica.desktop
/usr/share/metainfo/io.github.GenissonEmilio.citrica.metainfo.xml
/usr/share/icons/hicolor/scalable/apps/io.github.GenissonEmilio.citrica.svg
""")
    run("rpmbuild", "--define", f"_topdir {top}", "-bb", str(spec))
    for rpm in (top / "RPMS").rglob("*.rpm"):
        shutil.copy2(rpm, OUT / rpm.name)

checksums = []
for path in sorted(OUT.iterdir()):
    if path.name != "SHA256SUMS":
        checksums.append(f"{hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()}  {path.name}")
(OUT / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
