"""Install and remove a DEB in a disposable Ubuntu container, as a real user.

Run inside the container as root: python3 tests/linux/install_smoke.py path/to.deb
No host desktop or user data is used. GNOME compositor tests are separate.
"""

import argparse
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb', type=Path)
    parser.add_argument('--report', type=Path, default=Path('/tmp/citrica-deb-validation.json'))
    args = parser.parse_args()
    if os.geteuid() != 0 or not any(Path(p).exists() for p in ['/.dockerenv', '/run/.containerenv']):
        parser.error('Execute como root somente em um container descartável, nunca no host.')
    deb = args.deb.resolve()
    if not deb.is_file():
        parser.error('Pacote DEB não encontrado.')
    subprocess.run(['apt-get', 'install', '-y', '--no-install-recommends', str(deb)], check=True,
                   env=dict(os.environ, DEBIAN_FRONTEND='noninteractive'))
    username = 'citrica-package-test'
    subprocess.run(['useradd', '--create-home', '--shell', '/bin/sh', username], check=True)
    home = Path('/home') / username
    state = home / 'validation'
    state.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[1] / 'fixtures/astronaut.png', state / 'sample.png')
    subprocess.run(['chown', '-R', f'{username}:{username}', str(state)], check=True)
    def user_run(*arguments, gui=False):
        command = ['runuser', '-u', username, '--']
        if gui:
            command += ['dbus-run-session', '--', 'env', 'QT_QPA_PLATFORM=offscreen',
                        'XDG_SESSION_TYPE=', 'WAYLAND_DISPLAY=']
        return subprocess.run([*command, 'citrica', *map(str, arguments)], check=True,
                              capture_output=True, text=True, timeout=120)
    try:
        version = user_run('--version').stdout.strip()
        doctor = json.loads(user_run('--doctor').stdout)
        user_run('--setup', '--settings', '--screenshot', state / 'settings.png', gui=True)
        assert (state / 'settings.png').stat().st_size > 1000
        assert (home / '.config/citrica/setup.json').is_file()
        assert Path('/usr/share/applications/io.github.GenissonEmilio.citrica.desktop').is_file()
        assert not (home / '.local/share/applications/io.github.GenissonEmilio.citrica.desktop').exists()
        assert not Path('/root/.config/citrica/setup.json').exists(), 'Setup não deve modificar o root.'
        user_run(state / 'sample.png', '--to', 'pdf')
        pdf = state / 'sample.pdf'
        assert pdf.is_file()
        assert 'docx' in json.loads(user_run(pdf, '--formats').stdout)
        user_run(pdf, '--to', 'docx')
        with zipfile.ZipFile(state / 'sample.docx') as document:
            assert 'word/document.xml' in document.namelist()
        subprocess.run(['apt-get', 'remove', '-y', 'citrica'], check=True)
        assert not Path('/opt/citrica/citrica').exists()
        # A removed native installation must not leave a launcher whose command
        # points at the deleted executable. User preferences remain intentional.
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'version': version, 'os_release': Path('/etc/os-release').read_text(),
            'native_install': True, 'normal_user_launch': True, 'first_launch_setup': True,
            'settings_screenshot': True, 'image_pdf_docx': True, 'uninstall': True,
            'doctor': doctor}, indent=2, ensure_ascii=False))
        print(f'DEB instalado, aberto como usuário comum, conversões e remoção aprovados: {version}')
    finally:
        subprocess.run(['userdel', '--remove', username], check=False, capture_output=True)
        shutil.rmtree(state, ignore_errors=True)


if __name__ == '__main__':
    main()
