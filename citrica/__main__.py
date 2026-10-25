from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from citrica import __version__


def main():
    parser = argparse.ArgumentParser(description="Cítrica — conversor de arquivos local para Linux")
    parser.add_argument("files", type=Path, nargs="*")
    parser.add_argument("--version", action="version", version=f"Cítrica {__version__}")
    parser.add_argument("--to", metavar="FORMATO", help="converte sem abrir a interface")
    parser.add_argument("--output", type=Path, help="pasta de saída; padrão: junto ao original")
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--max-width", type=int, default=0)
    parser.add_argument("--keep-metadata", action="store_true")
    parser.add_argument("--dock", action="store_true", help="abre a roda nativa no desktop")
    parser.add_argument("--wheel", action="store_true", help="abre o menu radial para os arquivos")
    parser.add_argument("--formats", action="store_true", help="lista saídas disponíveis para os arquivos")
    parser.add_argument("--doctor", action="store_true", help="mostra dependências e ambiente")
    parser.add_argument("--merge-pdf", action="store_true")
    parser.add_argument("--install-integrations", action="store_true")
    parser.add_argument("--screenshot", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--settings", action="store_true", help="configurações e atalhos do desktop")
    parser.add_argument("--install-gnome", action="store_true", help="instala a roda global para GNOME 50")
    parser.add_argument("--desktop-request", help=argparse.SUPPRESS)
    parser.add_argument("--tool", help="abre uma ferramenta para os arquivos selecionados")
    parser.add_argument("--pick", action="store_true", help="escolhe arquivos para a roda")
    args = parser.parse_args()
    if args.desktop_request:
        from citrica.desktop import request
        try:
            print(json.dumps(request(json.loads(args.desktop_request)), ensure_ascii=False))
            return 0
        except Exception as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
    if args.install_gnome:
        from citrica.desktop import install_gnome
        print(json.dumps(install_gnome(), ensure_ascii=False, indent=2))
        return 0
    if args.settings or args.tool or args.pick:
        from citrica.companion import launch_companion
        return launch_companion(args)
    if args.install_integrations:
        from citrica.integration import install
        for path in install():
            print(path)
        return 0
    from citrica.core import Options, common_formats, convert, dependencies, merge_pdfs
    if args.doctor:
        import importlib.util
        import platform
        import shutil
        from citrica.desktop import extension_status
        from citrica.vision import text_available
        print(json.dumps({"version": __version__, "platform": platform.platform(),
                          "dependencies": dependencies(),
                          "tools": {"faces": importlib.util.find_spec('cv2') is not None,
                                    "text": text_available(),
                                    "qr": importlib.util.find_spec('zxingcpp') is not None,
                                    "share": shutil.which('localsend') is not None},
                          "desktop": extension_status()}, ensure_ascii=False, indent=2))
        return 0
    if args.formats:
        print(json.dumps(common_formats(args.files), ensure_ascii=False))
        return 0
    if args.to or args.merge_pdf:
        if not args.files:
            parser.error("informe ao menos um arquivo")
        try:
            opts = Options(args.quality, args.max_width, not args.keep_metadata)
        except ValueError as error:
            parser.error(str(error))
        cancel = threading.Event()
        failures = 0
        try:
            if args.merge_pdf:
                for path in merge_pdfs(args.files, args.output, cancel):
                    print(path)
            else:
                for source in args.files:
                    try:
                        for path in convert(source, args.to, args.output, opts, cancel):
                            print(path)
                    except Exception as error:
                        failures += 1
                        print(f"{source.name}: {error}", file=sys.stderr)
        except KeyboardInterrupt:
            cancel.set()
            return 130
        except Exception as error:
            print(str(error), file=sys.stderr)
            return 1
        return 1 if failures else 0
    if args.screenshot:
        from citrica.gui import launch
        return launch(args.files, False, False, args.screenshot)
    if args.dock or args.wheel or args.files:
        from citrica.companion import show_wheel
        try:
            show_wheel(args.files)
            return 0
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
    from citrica.companion import launch_companion
    return launch_companion(args)


if __name__ == "__main__":
    raise SystemExit(main())
