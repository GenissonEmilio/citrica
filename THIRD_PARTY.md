# Dependências e licenças

O código do Cítrica é distribuído sob AGPL-3.0-or-later. O pacote usa bibliotecas com licenças próprias, preservadas nos metadados e nas pastas de licenças incluídas no diretório `_internal`.

| Dependência | Licença / origem |
| --- | --- |
| PyMuPDF / MuPDF | AGPL-3.0-or-later; https://pymupdf.readthedocs.io/en/latest/about.html#license |
| PySide6 / Qt | LGPL-3.0 / GPL-3.0, conforme o componente; https://doc.qt.io/qtforpython-6/licenses.html |
| Shiboken6 | LGPL-3.0 / GPL-3.0; mesmo projeto Qt for Python |
| Pillow | HPND; https://github.com/python-pillow/Pillow |
| pillow-heif / libheif | BSD-3-Clause / LGPL-3.0; https://github.com/bigcat88/pillow_heif |
| pypdf | BSD-3-Clause; https://github.com/py-pdf/pypdf |
| Python | PSF-2.0; https://docs.python.org/3/license.html |
| PyInstaller | GPL-2.0-or-later com exceção para o bootloader; https://pyinstaller.org/en/stable/license.html |

Qt e as bibliotecas nativas permanecem dinamicamente vinculadas em `_internal`. Não é usado um executável monolítico que impeça substituir bibliotecas. Código-fonte do aplicativo, instruções de build e dependências estão disponíveis neste repositório. As bibliotecas subjacentes de codecs também têm seus avisos de licença nos pacotes das dependências.

FFmpeg e LibreOffice são executados separadamente, se instalados no sistema, e não são redistribuídos neste pacote. As respectivas licenças dependem da distribuição e dos codecs habilitados. Nenhum código, ícone, vídeo ou screenshot do Tangerine é redistribuído.
