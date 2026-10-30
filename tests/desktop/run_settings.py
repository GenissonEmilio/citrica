"""Save a custom chord and theme through the actual settings window."""
import json
import subprocess
import time

from run_flow import ENV, STATE, call, step, wait_for

TITLE = 'Cítrica · configurações'


def settings_window():
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        windows = json.loads(call('Test', 'Windows')[0])
        found = next((window for window in windows if window['title'] == TITLE), None)
        if found:
            return found
        time.sleep(.1)
    raise AssertionError(windows)


def click(window, x, y):
    """Coordinates are local to the 590×700 settings client, below Qt's CSD."""
    left, top, _width, height = window['rect']
    decoration = height - 700
    step('Pointer', left + x, top + decoration + y)
    step('Button', 'true')
    step('Button', 'false')


def main():
    step('Prepare')
    backend = json.loads((STATE / 'config/citrica/desktop.json').read_text())['command']
    settings_env = dict(ENV, GSETTINGS_SCHEMA_DIR=str(STATE /
                        'data/gnome-shell/extensions/citrica@genissonemilio.github.io/schemas'))
    def stored(key):
        return subprocess.check_output(['gsettings', 'get', 'org.gnome.shell.extensions.citrica', key],
                                       env=settings_env, text=True).strip()
    initial_shortcut, initial_theme = stored('toggle-wheel'), stored('wheel-theme')
    processes = []
    try:
        proc = subprocess.Popen([*backend, '--settings'], env=ENV)
        processes.append(proc)
        settings_window()
        # The complete window, including its title bar, fits the test monitor.
        step('PlaceWindow', TITLE, 200, 40)
        window = settings_window()
        (STATE / 'settings-window-layout.json').write_text(json.dumps(window))
        call('Test', 'Screenshot', str(STATE / 'settings-before-save.png'))
        click(window, 350, 142)  # Global-shortcut input on the General tab.
        print('settings-input-focus', call('Test', 'State'), window, flush=True)
        call('Test', 'Screenshot', str(STATE / 'settings-input-focus.png'))
        step('Key', 65507, 'true')
        step('Key', 97, 'true')
        step('Key', 97, 'false')
        step('Key', 65507, 'false')
        call('Test', 'Screenshot', str(STATE / 'settings-input-selected.png'))
        for char in 'Super+F8':
            call('Test', 'Key', ord(char), 'true')
            call('Test', 'Key', ord(char), 'false')
            time.sleep(.05)
        call('Test', 'Screenshot', str(STATE / 'settings-shortcut-typed.png'))
        click(window, 190, 64)  # Personalizar a roda.
        click(window, 293, 236)  # Aquarela, second preview card.
        click(window, 151, 668)  # Salvar atalho e preferências.
        wait_for(lambda s: s['shortcut'] == ['<Super>F8'] and s['wheelTheme'] == 'watercolor')
        assert stored('toggle-wheel') == "['<Super>F8']"
        assert stored('wheel-theme') == "'watercolor'"
        call('Test', 'Screenshot', str(STATE / 'settings-saved.png'))
        step('Key', 65307, 'true')
        step('Key', 65307, 'false')
        assert proc.wait(timeout=5) == 0
        # A new process must load both preferences. Saving/testing it without
        # another edit catches a picker or shortcut that silently resets on load.
        proc = subprocess.Popen([*backend, '--settings'], env=ENV)
        processes.append(proc)
        settings_window()
        step('PlaceWindow', TITLE, 200, 40)
        window = settings_window()
        click(window, 190, 64)
        call('Test', 'Screenshot', str(STATE / 'settings-theme-reloaded.png'))
        click(window, 438, 668)  # Salvar e testar roda.
        themed = wait_for(lambda s: s['visible'] and (s.get('motion') or {}).get('settled'))
        assert themed['shortcut'] == ['<Super>F8'] and themed['wheelTheme'] == 'watercolor'
        assert themed['motion']['theme'] == 'watercolor' and themed['paths'] == []
        assert proc.wait(timeout=5) == 0
        call('Test', 'Screenshot', str(STATE / 'settings-themed-wheel.png'))
        step('Key', 65307, 'true')
        step('Key', 65307, 'false')
        wait_for(lambda s: not s['visible'])
        for key in [65515, 65477]:
            step('Key', key, 'true')
        for key in [65477, 65515]:
            step('Key', key, 'false')
        wait_for(lambda s: s['visible'])
        step('Key', 65307, 'true')
        step('Key', 65307, 'false')
        wait_for(lambda s: not s['visible'])
        (STATE / 'settings-result.json').write_text(json.dumps({'settings_save': True,
            'saved_shortcut_invoked': True, 'theme_saved_by_actual_ui': 'watercolor',
            'theme_loaded_in_new_settings_process': True, 'save_and_test_opens_selected_theme': True}))
        print('Configurações reais: atalho e Aquarela salvos pela UI, recarregados e invocados no Wayland.')
    finally:
        subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'toggle-wheel',
                        initial_shortcut], env=settings_env, check=True)
        subprocess.run(['gsettings', 'set', 'org.gnome.shell.extensions.citrica', 'wheel-theme',
                        initial_theme], env=settings_env, check=True)
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)


if __name__ == '__main__':
    main()
