# Dependências e licenças

O código do Cítrica é distribuído sob AGPL-3.0-or-later. O pacote usa bibliotecas com licenças próprias, preservadas nos metadados e nas pastas de licenças incluídas no diretório `_internal`.

| Dependência | Licença / origem |
| --- | --- |
| PyMuPDF / MuPDF | AGPL-3.0-or-later; https://pymupdf.readthedocs.io/en/latest/about.html#license |
| PySide6 / Qt | LGPL-3.0 / GPL-3.0, conforme o componente; https://doc.qt.io/qtforpython-6/licenses.html |
| Shiboken6 | LGPL-3.0 / GPL-3.0; mesmo projeto Qt for Python |
| Pillow | MIT-CMU (Pillow 12.3); https://github.com/python-pillow/Pillow |
| pillow-heif / libheif | BSD-3-Clause / LGPL-3.0; https://github.com/bigcat88/pillow_heif |
| pypdf | BSD-3-Clause; https://github.com/py-pdf/pypdf |
| Python | PSF-2.0; https://docs.python.org/3/license.html |
| PyInstaller | GPL-2.0-or-later com exceção para o bootloader; https://pyinstaller.org/en/stable/license.html |

Qt e as bibliotecas nativas permanecem dinamicamente vinculadas em `_internal`. Não é usado um executável monolítico que impeça substituir bibliotecas. Código-fonte do aplicativo, instruções de build e dependências estão disponíveis neste repositório. As bibliotecas subjacentes de codecs também têm seus avisos de licença nos pacotes das dependências.

Os textos de LGPL-3.0 e GPL-3.0 do projeto Qt acompanham o pacote em `licenses/`. Qt/PySide6 e Shiboken6 não foram modificados. Suas fontes estão em https://code.qt.io/qt/qtbase.git/ e https://code.qt.io/pyside/pyside-setup.git/ (versão 6.12.0); as versões exatas das dependências Python estão em `requirements.lock`. O uso de versões modificadas dessas bibliotecas e a engenharia reversa para depurar modificações são permitidos nos termos das licenças aplicáveis.

Os programas de linha de comando FFmpeg e LibreOffice são executados separadamente, se instalados no sistema, e não são redistribuídos como executáveis neste pacote. As respectivas licenças dependem da distribuição e dos codecs habilitados. Nenhum código, ícone, vídeo ou screenshot do Tangerine é redistribuído.

A distribuição Windows 0.4.0 também usa Tesseract como dependência opcional externa, instalado pelo usuário; não inclui a DLL nem o modelo OCR no ZIP/instalador. A detecção local de rostos OpenCV e os motores de imagem/PDF/QR estão incluídos. As informações sobre Tesseract incluído no pacote, abaixo, referem-se à distribuição Linux.

## Visão local, QR e bibliotecas numéricas (0.2.0)

| Dependência | Licença / origem |
| --- | --- |
| OpenCV e modelo Haar de rostos | Apache-2.0 e avisos específicos preservados no XML; https://github.com/opencv/opencv |
| opencv-python-headless | MIT e licenças das bibliotecas nativas do wheel em LICENSE-3RD-PARTY.txt; https://github.com/opencv/opencv-python |
| NumPy / BLAS | BSD-3-Clause e avisos das bibliotecas incluídas no wheel; https://github.com/numpy/numpy |
| zxing-cpp | Apache-2.0; https://github.com/zxing-cpp/zxing-cpp |
| Tesseract e modelo tessdata eng | Apache-2.0; https://github.com/tesseract-ocr/tesseract e https://github.com/tesseract-ocr/tessdata |
| Leptonica | BSD-2-Clause; https://github.com/DanBloomberg/leptonica |

O pacote inclui a biblioteca Tesseract da distribuição de build, suas dependências nativas e eng.traineddata. Textos de licença, autores e avisos acompanham licenses/; no build Ubuntu os arquivos copyright dos pacotes libtesseract5, liblept5 e tesseract-ocr-eng também são copiados. As versões concretas são as do ambiente de build registrado no CI (Ubuntu 24.04); a execução por código-fonte usa as bibliotecas do sistema. A biblioteca OpenCV do wheel pode conter componentes FFmpeg, usados internamente pelo próprio OpenCV, com avisos preservados. O programa de linha de comando FFmpeg usado para conversões de mídia continua sendo instalado separadamente.

O metadado completo dos wheels OpenCV, NumPy e zxing-cpp é copiado para _internal, incluindo seus avisos de terceiros. A imagem NASA astronaut.png é somente um fixture de testes e não faz parte do aplicativo; a origem está em tests/fixtures/README.md. qrcode é uma dependência exclusiva dos testes (BSD-3-Clause), sem uso no executável.

## Documentos e integração Windows (0.5.0)

PDF→DOCX utiliza pdf2docx 0.5.13 (MIT), PyMuPDF e python-docx 1.2.0 (MIT). O projeto upstream pdf2docx informa que não recebe manutenção ativa da Artifex; a versão é fixada e validada pelos testes de conversão do Cítrica. FontTools (MIT), lxml/libxml2/libxslt (BSD/MIT), fire (Apache-2.0), termcolor (MIT) e typing_extensions (PSF) acompanham seus metadados/avisos no pacote. Textos de licença também estão em `licenses/`.

No Windows, pywin32 (licença PSF e avisos próprios) oferece a automação COM de leitura da seleção do Explorer. Não há redistribuição de Microsoft Word ou LibreOffice. A seleção antecipada é somente uma prévia; o arraste real confirma a operação. O código DOCX básico do Cítrica usa python-docx e o renderizador PyMuPDF.
