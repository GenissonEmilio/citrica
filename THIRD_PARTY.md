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

No Linux, FFmpeg e LibreOffice são executados separadamente a partir do sistema. O pacote Windows candidato 0.6.0 inclui motores offline em diretórios próprios; veja a seção específica abaixo. Nenhum código, ícone, vídeo ou screenshot do Tangerine é redistribuído.

As distribuições Windows 0.4.0/0.5.0 usam Tesseract como dependência opcional externa. A 0.6.0 candidata inclui a DLL e o modelo OCR. A detecção local de rostos OpenCV e os motores de imagem/PDF/QR permanecem incluídos nas duas plataformas.

## Visão local, QR e bibliotecas numéricas (0.2.0)

| Dependência | Licença / origem |
| --- | --- |
| OpenCV e modelo Haar de rostos | Apache-2.0 e avisos específicos preservados no XML; https://github.com/opencv/opencv |
| opencv-python-headless | MIT e licenças das bibliotecas nativas do wheel em LICENSE-3RD-PARTY.txt; https://github.com/opencv/opencv-python |
| NumPy / BLAS | BSD-3-Clause e avisos das bibliotecas incluídas no wheel; https://github.com/numpy/numpy |
| zxing-cpp | Apache-2.0; https://github.com/zxing-cpp/zxing-cpp |
| Tesseract e modelo tessdata eng | Apache-2.0; https://github.com/tesseract-ocr/tesseract e https://github.com/tesseract-ocr/tessdata |
| Leptonica | BSD-2-Clause; https://github.com/DanBloomberg/leptonica |

No Linux, o pacote inclui a biblioteca Tesseract da distribuição de build, suas dependências nativas e eng.traineddata. Textos de licença, autores e avisos acompanham licenses/; no build Ubuntu os arquivos copyright dos pacotes libtesseract5, liblept5 e tesseract-ocr-eng também são copiados. As versões concretas são as do ambiente de build registrado no CI; a execução por código-fonte usa as bibliotecas do sistema. A biblioteca OpenCV do wheel pode conter componentes FFmpeg, usados internamente pelo próprio OpenCV, com avisos preservados. O programa de linha de comando FFmpeg para conversões é externo no Linux e incluído no candidato Windows 0.6.0.

O metadado completo dos wheels OpenCV, NumPy e zxing-cpp é copiado para _internal, incluindo seus avisos de terceiros. A imagem NASA astronaut.png é somente um fixture de testes e não faz parte do aplicativo; a origem está em tests/fixtures/README.md. qrcode é uma dependência exclusiva dos testes (BSD-3-Clause), sem uso no executável.

## Documentos e integração Windows (0.5.0)

PDF→DOCX utiliza pdf2docx 0.5.13 (MIT), PyMuPDF e python-docx 1.2.0 (MIT). O projeto upstream pdf2docx informa que não recebe manutenção ativa da Artifex; a versão é fixada e validada pelos testes de conversão do Cítrica. FontTools (MIT), lxml/libxml2/libxslt (BSD/MIT), fire (Apache-2.0), termcolor (MIT) e typing_extensions (PSF) acompanham seus metadados/avisos no pacote. Textos de licença também estão em `licenses/`.

No Windows, pywin32 (licença PSF e avisos próprios) oferece a automação COM de leitura da seleção do Explorer. Microsoft Word não é redistribuído. A seleção antecipada é somente uma prévia; o arraste real confirma a operação. O código DOCX básico do Cítrica usa python-docx e o renderizador PyMuPDF.

## Motores Windows offline (candidato 0.6.0)

As origens, versões e SHA-256 ficam em `packaging/windows-engines.lock.json` e `packaging/windows-sources.lock.json`; o pacote registra os artefatos efetivamente usados em `_internal/engines.json` e seus arquivos em `engine-files.sha256.json`. As receitas estão em [docs/WINDOWS-ENGINES.md](docs/WINDOWS-ENGINES.md).

O caminho de publicação compila FFmpeg e OCR com fontes fixadas. O próprio bundle leva `_internal/engine-sources.zip` com os arquivos-fonte originais, as receitas e a configuração de compilação; o mesmo ZIP é disponibilizado separadamente junto do instalador. Os avisos das bibliotecas acompanham `tools/ffmpeg/licenses` e `ocr/licenses`. As bibliotecas permanecem substituíveis em diretórios normais; engenharia reversa para depuração das modificações permitidas pelas licenças não é proibida.

| Componente | Licença / fontes |
| --- | --- |
| FFmpeg 9.0.2, com `--enable-gpl --enable-version3` | GPL-3.0-or-later; [fontes oficiais](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz) e fontes correspondentes no ZIP incluído |
| x264 stable b35605ace3dd | GPL-2.0-or-later; [VideoLAN](https://code.videolan.org/videolan/x264/-/tree/b35605ace3ddf7c1a5d67a2eb553f034aef41d55) |
| libvpx 1.17.0 | BSD-3-Clause e PATENTS preservados; [WebM](https://github.com/webmproject/libvpx/tree/v1.17.0) |
| Opus 1.5.2 / libogg 1.3.6 / libvorbis 1.3.7 | BSD e concessões de patentes nos respectivos arquivos; [Xiph](https://downloads.xiph.org/releases/) |
| LAME 3.100 | LGPL-2.0-or-later; [fontes LAME](https://sourceforge.net/projects/lame/files/lame/3.100/) |
| dav1d 1.5.4 | BSD-2-Clause; [VideoLAN](https://code.videolan.org/videolan/dav1d/-/tree/54706fc6bc0cdecab7e9593974a4039cc038fca7) |
| zlib 1.3.2 | zlib; [fontes oficiais](https://zlib.net/fossils/zlib-1.3.2.tar.gz) |
| Tesseract 5.5.3 / Leptonica 1.87.0 | Apache-2.0 / BSD-2-Clause; [Tesseract](https://github.com/tesseract-ocr/tesseract/tree/db0ec62f81b0737fbbe184d8fea40af5738f8eef), [Leptonica](https://github.com/DanBloomberg/leptonica/releases/tag/1.87.0) |
| eng.traineddata | Apache-2.0; [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd) |
| LibreOffice 26.2.6 | MPL-2.0 e avisos de terceiros completos preservados no diretório Office; [licenciamento oficial](https://www.libreoffice.org/licenses/), [fontes dessa versão](https://download.documentfoundation.org/libreoffice/src/26.2.6/) |

FFmpeg para conversão roda como processo separado. As fontes correspondentes também abrangem as bibliotecas de codec que ligamos estaticamente ao FFmpeg. OCR usa Tesseract ligado a Leptonica, sem CURL/Archive/leitores de codecs; a imagem já chega decodificada como RGB. Os toolchains e seus avisos são registrados na receita; Microsoft Visual C++ Runtime mantém seus termos próprios de redistribuição e não passa a ser AGPL. A prévia multimídia adicionada na 0.7.0 usa separadamente as bibliotecas dinâmicas fornecidas pelo Qt, descritas abaixo.

Para testes funcionais internos existe um preparador provisório que extrai os binários Gyan/UB Mannheim fixados por hash. Esse caminho tem procedência `provisional-vendor-binaries` e não estabelece sozinho as fontes correspondentes de todas as bibliotecas desses builds. `CITRICA_RELEASE_REQUIRE_ENGINE_SOURCES=1` recusa esse caminho para publicação. Não se afirma que o candidato provisório já passou pela verificação de licenças, certificação ou reputação de segurança.

## Prévia de áudio e vídeo (0.7.0)

O player interno usa Qt Multimedia e Qt Multimedia Widgets do PySide6-Addons 6.12.0, sob LGPL-3.0 / GPL conforme o componente, sem modificações. O pacote copia seus metadados e preserva as bibliotecas dinâmicas e o plugin de mídia em `_internal/PySide6`; seus avisos de terceiros completos estão em `licenses/QtMultimedia-NOTICES.txt`. Não são incluídos WebEngine nem um navegador para reproduzir os arquivos.

O backend do Qt 6.12 utiliza FFmpeg 9.0.1, distribuído pelo próprio Qt sob LGPL-2.1-or-later e licenças permissivas, além de DR Libs, Signalsmith Stretch, TLSF, Boost, libjpeg e zlib. Isso é independente do executável FFmpeg 9.0.2 usado para conversões Windows. [Atribuições oficiais do Qt Multimedia](https://doc.qt.io/qt-6/qtmultimedia-index.html#licenses-and-attributions), [atribuições FFmpeg](https://doc.qt.io/qt-6/qtmultimedia-attribution-ffmpeg.html), [fontes Qt Multimedia 6.12.0](https://code.qt.io/cgit/qt/qtmultimedia.git/tree/?h=v6.12.0), [receitas oficiais do backend FFmpeg](https://code.qt.io/cgit/qt/qt5.git/tree/coin/provisioning) e [fontes FFmpeg 9.0.1](https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz).

Não é impedida a substituição dessas bibliotecas nem a engenharia reversa para depurar alterações permitidas pelas licenças. A prévia depende dos codecs suportados pelo backend; falhas de reprodução são informadas no editor, com miniaturas e navegação de quadros como alternativa. Exportações continuam usando os motores de conversão próprios, sem depender do player.

No Linux, a prévia de áudio também utiliza as bibliotecas dinâmicas PulseAudio da distribuição de build. O pacote Ubuntu preserva os avisos de `libpulse0` e o texto LGPL-2.1 em `licenses/`. As bibliotecas não foram modificadas; as fontes correspondentes são fornecidas pela distribuição de build e pelo projeto PulseAudio.
