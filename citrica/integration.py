"""Opt-in, user-scoped desktop integration. Never requires root."""

import os
import shlex
import shutil
import sys
from pathlib import Path


def command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    executable = shutil.which("citrica")
    if executable:
        return [executable]
    return [sys.executable, "-m", "citrica"]


def desktop_exec(parts):
    # Desktop Entry Exec quoting differs from shell quoting.
    return " ".join('"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
                    .replace("$", "\\$").replace("%", "%%") + '"' for arg in parts)


def install(data_home: Path | None = None, *, include_application=True) -> list[Path]:
    root = data_home or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    cmd = command()
    executable = desktop_exec(cmd)
    files = {
        "applications/io.github.GenissonEmilio.citrica.desktop":
            "[Desktop Entry]\nType=Application\nName=Cítrica\nComment=Conversor local de arquivos\n"
            f"Exec={executable} %F\nIcon=io.github.GenissonEmilio.citrica\nTerminal=false\n"
            "Categories=Utility;Graphics;AudioVideo;\nKeywords=convert;converter;pdf;image;offline;\n"
            "MimeType=image/png;image/jpeg;image/webp;application/pdf;video/mp4;audio/mpeg;\n",
        "kio/servicemenus/citrica.desktop":
            "[Desktop Entry]\nType=Service\nMimeType=all/allfiles;\nActions=citrica;\n"
            "X-KDE-Priority=TopLevel\n\n[Desktop Action citrica]\nName=Converter com Cítrica\n"
            f"Icon=io.github.GenissonEmilio.citrica\nExec={executable} --wheel %F\n",
        "nemo/actions/citrica.nemo_action":
            "[Nemo Action]\nName=Converter com Cítrica\nComment=Conversão local\n"
            f"Exec={executable} --wheel %F\nIcon-Name=io.github.GenissonEmilio.citrica\n"
            "Selection=notnone\nExtensions=any;\nQuote=double\n",
        "nautilus/scripts/Converter com Cítrica":
            "#!/bin/sh\nexec " + shlex.join(cmd) + ' --wheel "$@"\n',
        "nautilus-python/extensions/citrica.py":
            "from gi.repository import GObject, Nautilus\nfrom urllib.parse import urlparse, unquote\n"
            "import subprocess\n\nclass CitricaMenu(GObject.GObject, Nautilus.MenuProvider):\n"
            "    def get_file_items(self, files):\n"
            "        paths = [unquote(urlparse(f.get_uri()).path) for f in files\n"
            "                 if f.get_uri_scheme() == 'file' and not f.is_directory()]\n"
            "        if not paths:\n            return []\n"
            "        item = Nautilus.MenuItem(name='Citrica::convert', label='Converter com Cítrica',\n"
            "                                 tip='Conversão local de arquivos')\n"
            f"        item.connect('activate', lambda *_: subprocess.Popen({cmd!r} + ['--wheel'] + paths))\n"
            "        return [item]\n",
    }
    result = []
    for relative, content in files.items():
        if not include_application and relative.startswith('applications/'):
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if relative.startswith("nautilus/scripts/"):
            path.chmod(0o755)
        result.append(path)
    if not include_application:
        return result
    icon = root / "icons/hicolor/scalable/apps/io.github.GenissonEmilio.citrica.svg"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).parent / "assets/citrica.svg", icon)
    return result + [icon]
