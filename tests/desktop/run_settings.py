"""Save and invoke a custom chord through the real settings window."""
import json
import subprocess
import time

from run_flow import ENV, STATE, call, step, wait_for


def main():
    step('Prepare')
    backend = json.loads((STATE / 'config/citrica/desktop.json').read_text())['command']
    proc = subprocess.Popen([*backend, '--settings'], env=ENV)
    settings_env = dict(ENV, GSETTINGS_SCHEMA_DIR=str(STATE /
                        'data/gnome-shell/extensions/citrica@genissonemilio.github.io/schemas'))
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            windows = json.loads(call('Test', 'Windows')[0])
            if any(w['title'] == 'Cítrica · configurações' for w in windows):
                break
            time.sleep(.1)
        assert any(w['title'] == 'Cítrica · configurações' for w in windows)
        step('PlaceWindow', 'Cítrica · configurações', 200, 100)
        step('Pointer', 500, 340)
        step('Button', 'true')
        step('Button', 'false')
        step('Key', 65507, 'true')
        step('Key', 97, 'true')
        step('Key', 97, 'false')
        step('Key', 65507, 'false')
        for char in 'Super+F8':
            call('Test', 'Key', ord(char), 'true')
            call('Test', 'Key', ord(char), 'false')
        step('Pointer', 340, 490)
        step('Button', 'true')
        step('Button', 'false')
        wait_for(lambda s: s['shortcut'] == ['<Super>F8'])
        call('Test', 'Screenshot', str(STATE / 'settings-saved.png'))
        for key in [65515, 65477]:
            step('Key', key, 'true')
        for key in [65477, 65515]:
            step('Key', key, 'false')
        wait_for(lambda s: s['visible'])
        step('Key', 65307, 'true')
        step('Key', 65307, 'false')
        wait_for(lambda s: not s['visible'])
        (STATE / 'settings-result.json').write_text(json.dumps({'settings_save': True, 'saved_shortcut_invoked': True}))
        print('Configurações reais: atalho salvo pela interface e invocado globalmente no Wayland.')
    finally:
        subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'toggle-wheel',
                        "['<Super><Shift>c']"], env=settings_env, check=True)
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == '__main__':
    main()
