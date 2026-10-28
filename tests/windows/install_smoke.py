"""Install/uninstall the actual per-user EXE on a dedicated Windows CI runner."""
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, timeout=180, **kwargs)


def main():
    import winreg
    setup = Path(sys.argv[1]).resolve()
    target = ROOT / 'build/windows-installer/Citrica'
    target.parent.mkdir(parents=True, exist_ok=True)
    install_log = target.parent / 'install.log'
    run(setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={target}', f'/LOG={install_log}')
    cli, gui = target / 'citrica-cli.exe', target / 'Citrica.exe'
    assert cli.is_file() and gui.is_file() and (target / '_internal').is_dir()
    version = run(cli, '--version', capture_output=True, text=True, encoding='utf-8').stdout.strip()
    assert version == f'Cítrica {VERSION}', version
    sendto = Path(os.environ['APPDATA']) / 'Microsoft/Windows/SendTo/Cítrica.lnk'
    assert sendto.is_file(), 'Enviar para shortcut was not installed'
    # Upgrades must replace the complete private runtime: a removed OCR/Qt DLL
    # must not survive and be loaded instead of the newly bundled engine.
    obsolete = target / '_internal/ocr/obsolete-runtime.dll'
    obsolete.parent.mkdir(parents=True, exist_ok=True)
    obsolete.write_bytes(b'previous-version fixture')
    run(setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={target}',
        f'/LOG={target.parent / "upgrade.log"}')
    assert not obsolete.exists(), 'An obsolete bundled DLL survived the upgrade'
    assert run(cli, '--version', capture_output=True, text=True, encoding='utf-8').stdout.strip() == version
    (ROOT / 'release').mkdir(exist_ok=True)
    run(gui, '--settings', '--screenshot', ROOT / 'release/citrica-windows-installed-preview.png',
        env=dict(os.environ, QT_QPA_PLATFORM='windows'))
    # Simulate enabling startup through preferences after installation, then
    # check that uninstall removes that user-owned entry as well.
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        winreg.SetValueEx(key, 'Citrica', 0, winreg.REG_SZ, f'"{gui}" --background')
    uninstaller = target / 'unins000.exe'
    assert uninstaller.is_file()
    run(uninstaller, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        f'/LOG={target.parent / "uninstall.log"}')
    assert not gui.exists() and not cli.exists() and not sendto.exists()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        try:
            winreg.QueryValueEx(key, 'Citrica')
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Startup entry remained after uninstall')
    result = {'per_user_install': True, 'installed_cli_version': version, 'sendto_shortcut': True,
              'installed_gui_launch': True, 'upgrade_replaces_runtime': True,
              'uninstall': True, 'startup_entry_removed': True}
    (ROOT / 'release/citrica-windows-installer-validation.json').write_text(json.dumps(result, indent=2),
                                                                          encoding='utf-8')
    print('Instalador Windows: instalação no usuário, aplicativo, Enviar para e desinstalação passaram.')


if __name__ == '__main__':
    main()
