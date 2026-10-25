"""Environment for system programs called by the portable application."""
import os


def external_environment():
    env = os.environ.copy()
    # PyInstaller and Qt prepend bundled libraries/plugins. System programs must
    # use their own libraries, especially across Ubuntu-build/Fedora-runtime.
    original = env.get('LD_LIBRARY_PATH_ORIG')
    if original is not None:
        env['LD_LIBRARY_PATH'] = original
    else:
        env.pop('LD_LIBRARY_PATH', None)
    env.pop('QT_PLUGIN_PATH', None)
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    return env
