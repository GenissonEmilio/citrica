<p align="center"><img src="citrica/assets/citrica.svg" width="88" alt="Cítrica"></p>
<h1 align="center">Cítrica</h1>
<p align="center">Arraste. Pressione Shift. Solte no formato.<br>Conversão local no desktop Linux e Windows.</p>
<p align="center"><a href="https://github.com/GenissonEmilio/citrica/releases/tag/v0.4.0">Baixar para Linux</a> · <a href="docs/VALIDACAO.md">Validação e limites</a> · <a href="docs/ANALISE.md">Referência e decisões</a></p>

![Roda nativa durante um arraste no GNOME 50/Wayland](docs/wheel.png)

O Cítrica 0.4 oferece a roda nativa do GNOME Shell no Linux e uma integração Qt/Win32 no Windows. A roda aparece perto do ponteiro durante o arraste de arquivos. A janela do aplicativo serve para configurar o atalho; ferramentas que precisam de parâmetros abrem um diálogo específico.

**Nesta versão:** a roda reabre vazia após converter ou cancelar, e usa setores claros com miniatura, destaque laranja e animações de abertura/seleção/fechamento. [Veja a gravação nativa](docs/wheel-native.mp4) e a [análise visual](docs/ANALISE.md).

Implementação independente inspirada no fluxo do [Tangerine](https://www.tangerineformac.com/), com código e identidade próprios. Não é afiliada ao produto comercial e não oferece todas as suas combinações de formatos.

## Windows x64

Baixe o [instalador .exe](https://github.com/GenissonEmilio/citrica/releases/download/v0.4.0/citrica-0.4.0-windows-x86_64-setup.exe) ou o [ZIP portátil](https://github.com/GenissonEmilio/citrica/releases/download/v0.4.0/citrica-0.4.0-windows-x86_64-portable.zip). O instalador usa a conta atual e cria a entrada **Enviar para → Cítrica**. No portátil, extraia tudo e abra `Citrica.exe` mantendo `_internal` ao lado.

Arraste no Explorer, pressione **Shift** e solte no formato. **Alt** abre ferramentas; **Ctrl**, ações. **Ctrl+Alt+C** abre/fecha a roda. O aplicativo permanece na bandeja ao fechar as configurações. O atalho e a inicialização automática são configuráveis.

Python, Qt, motores de imagem/PDF, QR e detecção de rostos estão incluídos. **FFmpeg/ffprobe, LibreOffice e Tesseract são opcionais externos no Windows.** O instalador ainda não tem assinatura digital. A validação manual do fluxo no Explorer está pendente do teste externo combinado; os resultados automatizados estão na documentação.

![Roda em execução nativa no Windows do CI](docs/windows-wheel.png)

Veja o [guia de instalação e roteiro de teste no Windows](docs/WINDOWS.md).

## Fedora / GNOME 50 / Wayland

Demonstração no Fedora: arraste o arquivo, escolha o formato na roda e receba a cópia convertida. [Baixar o vídeo em MP4](docs/citrica-linux.mp4).

https://github.com/user-attachments/assets/812f2703-e781-4b44-a544-3829eae95688

Baixe o RPM da [release v0.4.0](https://github.com/GenissonEmilio/citrica/releases/tag/v0.4.0):

~~~bash
sudo dnf install ./citrica-0.4.0-1.x86_64.rpm
citrica --install-gnome
~~~

Na primeira instalação, **saia e entre novamente na sessão do GNOME** para ele descobrir a extensão. Atualizações do código da extensão também exigem uma nova sessão; fechar o aplicativo não recarrega o Shell. As configurações informam se a sessão ainda está usando uma revisão anterior.

1. No gerenciador de arquivos, comece a arrastar uma imagem.
2. Toque **Shift** e solte a tecla. A roda aparece com os formatos compatíveis.
3. Continue arrastando e solte o arquivo no setor **JPG**, por exemplo.
4. Uma cópia aparece junto ao original; uma notificação confirma a conclusão.

**Alt** durante o arraste mostra ferramentas. **Ctrl** mostra ações. **Esc** cancela. O atalho **Super+Shift+C** abre/fecha a roda sem iniciar um arraste. Sem seleção, arraste um arquivo para ela ou clique no centro para escolher arquivos. Para várias páginas de opções, use **Mais** e clique na ferramenta desejada. Setas e Enter também selecionam e aplicam opções.

Abra **Cítrica** no menu de aplicativos ou execute `citrica --settings` para trocar o atalho, escolher Shift/Super durante o arraste e ligar/desligar a animação. O formulário verifica teclas inválidas e conflitos com atalhos registrados no GNOME.

![Configurações do Cítrica](docs/settings.png)

No Linux, a integração global desta versão suporta **GNOME Shell 50**. A CLI funciona em outros ambientes, mas não há roda global equivalente para KDE, Cinnamon ou X11 nesta release. RPM/DEB/portátil são x86_64, com glibc >= 2.39. O CI Linux compila no Ubuntu 24.04; instalar o DEB nesse sistema não acrescenta suporte à versão antiga do GNOME que ele utiliza.

## Outros pacotes e dependências

~~~bash
# DEB, para sistemas compatíveis com as bibliotecas indicadas acima
sudo apt install ./citrica_0.4.0_amd64.deb
# Portátil, sem precisar instalar Python
 tar -xzf citrica-0.4.0-linux-x86_64.tar.gz
 ./citrica/install.sh
~~~

O instalador portátil registra o aplicativo em `~/.local/bin/citrica`, configura a extensão e instala menus de contexto no usuário atual. O RPM/DEB registra o aplicativo no sistema; `citrica --install-gnome` instala a extensão no usuário atual. Para menus de contexto opcionais, execute `citrica --install-integrations`. O script do Nautilus funciona sem plugin adicional; a entrada direta exige `nautilus-python`. As integrações Nemo/Dolphin continuam sendo alternativas para chamar a CLI/seleção; a roda requer GNOME 50.

Os pacotes Linux incluem Python, Qt, Pillow, motores PDF, leitor QR, modelo de rostos OpenCV e Tesseract com modelo de texto inglês. **FFmpeg e LibreOffice são programas opcionais do sistema**:

~~~bash
# Fedora: LibreOffice; use um FFmpeg com os codecs desejados habilitados
sudo dnf install libreoffice
# Debian/Ubuntu
sudo apt install ffmpeg libreoffice
citrica --doctor
~~~

Mídia exige FFmpeg/ffprobe; codecs variam entre instalações. Falhas de codec são informadas sem alterar a origem. LocalSend é opcional para compartilhamento, aparece nas ações somente quando o comando `localsend` está disponível e abre o aplicativo para concluir o envio. AirDrop não está implementado.

Confira `SHA256SUMS` na pasta dos downloads. Mantenha `_internal` junto ao executável portátil. A extensão e seu backend precisam continuar no caminho registrado; reinstale a integração se mover o aplicativo.

## Ferramentas

As opções dependem do tipo de arquivo e das dependências disponíveis. As ferramentas geram cópias; **Mover** é a ação explícita que muda o local do original.

| Grupo | Ferramentas implementadas |
| --- | --- |
| Imagem | Comprimir, tamanho alvo, recortar visualmente, brilho/contraste/saturação/nitidez, anotar com texto/número/seta/retângulo/elipse, fundo sólido/gradiente/imagem, margens/proporção/cantos, ocultar área manualmente, ocultar rostos, ocultar texto, ler QR, colagem, imagens em PDF |
| Áudio/vídeo | Comprimir, tamanho alvo, cortar tempo, velocidade, dividir, unir seleções compatíveis; recortar vídeo e capturar quadro; normalizar áudio, censurar trecho com tom e converter mono/estéreo |
| PDF | Comprimir, tamanho alvo, unir, dividir em páginas, reorganizar páginas |
| Metadados | Inspecionar, limpar e editar autor/título em imagens, PDF, áudio e vídeo |
| Ações | Copiar, mover, copiar caminho, abrir terminal, prateleira flutuante, compartilhar por LocalSend quando instalado |

Há 26 entradas de ferramentas e 6 ações no catálogo, com equivalentes adaptados ao Linux. Isso **não representa paridade completa** com cada função/algoritmo do Tangerine. Veja o [escopo testado](docs/VALIDACAO.md).

O tamanho alvo publica somente resultados que respeitam o limite solicitado; se não conseguir, informa falha. Imagens saem em WebP e podem perder resolução; áudio sai em MP3 e vídeo em MP4. PDF preserva o texto e comprime imagens internas; pode não atingir limites muito baixos. Detecção de rosto/texto pode deixar áreas sem identificar: revise a cópia e use ocultação manual quando necessário. O modelo de texto incluído é inglês; este recurso oculta regiões de texto e não exporta documentos escaneados por OCR.

## Conversões

| Entrada | Saída | Motor |
| --- | --- | --- |
| JPG, PNG, WebP, TIFF, BMP, GIF, AVIF, HEIC/HEIF | PNG, JPG, WebP, AVIF, HEIC, TIFF, BMP, GIF, PDF | Pillow + pillow-heif |
| PDF | PNG/JPG por página, TXT, PDF | PyMuPDF + pypdf |
| MP4, MOV, MKV, AVI, WebM, WMV, M4V, MPEG | MP4, WebM, MKV, MOV, GIF, MP3, WAV | FFmpeg |
| MP3, WAV, FLAC, OGG, Opus, M4A, MKA, AAC, AIFF, WMA | MP3, WAV, FLAC, OGG, Opus, M4A, AIFF | FFmpeg |
| DOC/DOCX, ODT, RTF, TXT | PDF, DOCX, ODT, TXT | LibreOffice; TXT→PDF interno |
| XLS/XLSX, ODS, CSV, TSV | PDF, XLSX, ODS, CSV | LibreOffice |
| PPT/PPTX, ODP | PDF, PPTX, ODP | LibreOffice |
| SRT, VTT | SRT, VTT, TXT | Interno |
| ZIP, TAR, TAR.GZ, TGZ | ZIP, TAR, TAR.GZ | Python |

Saídas são publicadas atomicamente, junto ao original por padrão; nomes repetidos recebem sufixos. Imagens animadas/multipágina são recusadas para evitar perda de quadros. SVG, RAR, Pages, EPUB e PDF→Office não estão implementados. Office depende do LibreOffice e seus filtros; a limpeza de metadados não cobre documentos Office. Legendas preservam texto e tempos básicos, sem estilos específicos. Arquivos compactados são reempacotados, sem extração pública; links, nomes inseguros e entradas duplicadas são recusados (10.000 entradas / 2 GiB descompactados).

## Terminal e desenvolvimento

~~~bash
citrica foto.heic --to jpg
citrica *.png --to webp --quality 80 --max-width 1920
citrica documento.pdf --to png --output ./paginas
citrica a.pdf b.pdf --merge-pdf --output ./resultado
citrica video.mov --to mp4
citrica foto.png --formats
citrica --wheel foto.png
citrica --tool crop foto.png
~~~

Python 3.12 ou superior:

~~~bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check citrica tests packaging
# Teste real do compositor, somente em GNOME 50 instalado:
python tests/desktop/run_session.py
# Pacotes com PyInstaller, RPM/DEB quando as ferramentas estão instaladas:
python packaging/build.py
~~~

O teste do desktop cria outro compositor GNOME/Wayland com barramento e configurações isolados. A extensão de teste nunca é instalada no desktop do usuário nem incluída nos pacotes. O CI verifica o motor e o executável empacotado; o teste GNOME 50 é executado separadamente no Fedora. [Detalhes e evidências](docs/VALIDACAO.md).

## Licença

[AGPL-3.0-or-later](LICENSE). Dependências e avisos em [THIRD_PARTY.md](THIRD_PARTY.md). Os arquivos não são enviados para serviços externos durante conversões; o compartilhamento só abre o aplicativo escolhido por uma ação explícita.
