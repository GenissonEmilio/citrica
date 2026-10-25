"""Build portable and native Linux packages from the same dynamically linked payload."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from citrica import __version__
from smoke import verify

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
OUT = ROOT / "release"
OUT.mkdir(exist_ok=True)


def run(*args):
    subprocess.run(list(args), check=True)


run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "citrica",
    "--onedir", "--add-data", "citrica/assets:citrica/assets", "--collect-all", "pillow_heif",
    "--collect-all", "pymupdf", "--copy-metadata", "Pillow", "--copy-metadata", "pypdf",
    "--copy-metadata", "PyMuPDF", "--copy-metadata", "PySide6-Essentials",
    "--copy-metadata", "shiboken6", "packaging/entry.py")

payload = ROOT / "dist/citrica"
for name in ["README.md", "LICENSE", "THIRD_PARTY.md"]:
    shutil.copy2(ROOT / name, payload / name)
shutil.copy2(ROOT / "packaging/install.sh", payload / "install.sh")
(payload / "install.sh").chmod(0o755)
run(str(payload / "citrica"), "--doctor")
verify(payload / "citrica")
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
subprocess.run([str(payload / "citrica"), "--screenshot", str(OUT / "citrica-preview.png")], env=env, check=True)
run("tar", "-czf", str(OUT / f"citrica-{__version__}-linux-x86_64.tar.gz"), "-C", str(ROOT / "dist"), "citrica")

if shutil.which("dpkg-deb"):
    deb = ROOT / "build/deb"
    if deb.exists():
        shutil.rmtree(deb)
    shutil.copytree(payload, deb / "opt/citrica")
    (deb / "usr/bin").mkdir(parents=True)
    (deb / "usr/bin/citrica").symlink_to("/opt/citrica/citrica")
    desktop = deb / "usr/share/applications"
    desktop.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/io.github.GenissonEmilio.citrica.desktop", desktop)
    icons = deb / "usr/share/icons/hicolor/scalable/apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "citrica/assets/citrica.svg", icons / "io.github.GenissonEmilio.citrica.svg")
    control = deb / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: citrica\nVersion: {__version__}\nArchitecture: amd64\n"
        "Maintainer: GenissonEmilio <GenissonEmilio@users.noreply.github.com>\nSection: utils\nPriority: optional\n"
        "Depends: libc6 (>= 2.39), libgl1, libegl1, libxkbcommon0, libxcb-cursor0, libdbus-1-3, "
        "libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-xinerama0, libxcb-randr0, "
        "libxcb-render-util0, libxcb-xfixes0, libxkbcommon-x11-0, libfontconfig1, libglib2.0-0t64\n"
        "Recommends: ffmpeg, libreoffice\nHomepage: https://github.com/GenissonEmilio/citrica\n"
        "Description: Conversor local de arquivos com menu radial para Linux\n"
        " Converta imagens, PDF, mídia, documentos, legendas e arquivos sem upload.\n")
    run("dpkg-deb", "--build", "--root-owner-group", str(deb), str(OUT / f"citrica_{__version__}_amd64.deb"))

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
Requires: glibc >= 2.39
Requires: libglvnd-glx, libglvnd-egl, libxkbcommon, libxcb, xcb-util-cursor, fontconfig, dbus-libs
Requires: xcb-util-wm, xcb-util-keysyms, xcb-util-image, xcb-util-renderutil, libxkbcommon-x11
Recommends: ffmpeg, libreoffice
%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%description
Conversor offline de imagens, PDF, áudio, vídeo, documentos e legendas.
%install
mkdir -p %{{buildroot}}/opt %{{buildroot}}/usr/bin %{{buildroot}}/usr/share/applications
cp -a "{payload}" %{{buildroot}}/opt/citrica
ln -s /opt/citrica/citrica %{{buildroot}}/usr/bin/citrica
cp "{ROOT}/packaging/io.github.GenissonEmilio.citrica.desktop" %{{buildroot}}/usr/share/applications/
mkdir -p %{{buildroot}}/usr/share/icons/hicolor/scalable/apps
cp "{ROOT}/citrica/assets/citrica.svg" %{{buildroot}}/usr/share/icons/hicolor/scalable/apps/io.github.GenissonEmilio.citrica.svg
%files
/opt/citrica
/usr/bin/citrica
/usr/share/applications/io.github.GenissonEmilio.citrica.desktop
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
