"""Native Linux package metadata, independently testable from PyInstaller."""

import platform
import re
import shutil
import subprocess
from pathlib import Path


def glibc_floor():
    """Do not advertise an older libc than the machine building the payload.

    PyInstaller does not bundle libc. Official payloads are built on Ubuntu 24.04;
    a developer's Fedora build must not accidentally claim the same ABI floor.
    """
    name, version = platform.libc_ver()
    if name != 'glibc' or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        raise RuntimeError('Compile os pacotes Linux em um sistema com glibc identificável.')
    return version


def build_deb(root: Path, payload: Path, output: Path, version: str):
    staging = root / 'build/deb'
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(payload, staging / 'opt/citrica')
    (staging / 'usr/bin').mkdir(parents=True)
    (staging / 'usr/bin/citrica').symlink_to('/opt/citrica/citrica')
    applications = staging / 'usr/share/applications'
    applications.mkdir(parents=True)
    shutil.copy2(root / 'packaging/io.github.GenissonEmilio.citrica.desktop', applications)
    metainfo = staging / 'usr/share/metainfo'
    metainfo.mkdir(parents=True)
    shutil.copy2(root / 'packaging/io.github.GenissonEmilio.citrica.metainfo.xml', metainfo)
    icons = staging / 'usr/share/icons/hicolor/scalable/apps'
    icons.mkdir(parents=True)
    shutil.copy2(root / 'citrica/assets/citrica.svg', icons / 'io.github.GenissonEmilio.citrica.svg')
    control = staging / 'DEBIAN'
    control.mkdir()
    (control / 'control').write_text(
        f'Package: citrica\nVersion: {version}\nArchitecture: amd64\n'
        'Maintainer: GenissonEmilio <GenissonEmilio@users.noreply.github.com>\n'
        'Section: utils\nPriority: optional\n'
        f'Installed-Size: {sum(p.stat().st_size for p in payload.rglob("*") if p.is_file()) // 1024}\n'
        f'Depends: libc6 (>= {glibc_floor()}), libgl1, libegl1, libxkbcommon0, libxcb-cursor0, '
        'libdbus-1-3, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-xinerama0, '
        'libxcb-randr0, libxcb-render-util0, libxcb-xfixes0, libxkbcommon-x11-0, '
        'libfontconfig1, libwayland-client0, libwayland-cursor0, libwayland-egl1, '
        'libglib2.0-0t64 | libglib2.0-0, libglib2.0-bin, python3-gi\n'
        'Recommends: ffmpeg, libreoffice, gnome-shell, libtesseract5, tesseract-ocr-eng\n'
        'Homepage: https://github.com/GenissonEmilio/citrica\n'
        'Description: Conversor local de arquivos com menu radial para Linux\n'
        ' Converta imagens, PDF, mídia, documentos, legendas e arquivos sem upload.\n'
        ' Roda global em GNOME 46/50/51 com sessão Wayland.\n', encoding='utf-8')
    # Run as root only for system caches. User setup happens in the first desktop
    # launch, in the actual user's session, never in a package-manager HOME.
    cache_update = ('#!/bin/sh\nset -e\n'
                    'if command -v update-desktop-database >/dev/null 2>&1; then\n'
                    '    update-desktop-database -q /usr/share/applications || true\nfi\n'
                    'if command -v gtk-update-icon-cache >/dev/null 2>&1; then\n'
                    '    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true\nfi\n')
    for name in ['postinst', 'postrm']:
        (control / name).write_text(cache_update)
        (control / name).chmod(0o755)
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'citrica_{version}_amd64.deb'
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(staging), str(target)], check=True)
    return target
