# Validação da candidata 0.6.0

A candidata inclui os motores de conversão no Windows e corrige a instalação do DEB e a integração com GNOME 46/50/51. Ainda não é uma release pública assinada. O histórico da versão pública permanece em [VALIDACAO.md](VALIDACAO.md).

## Windows 11 em máquina virtual

Foi usada uma VM separada com Windows 11 Pro x64 em português, build 26300.9457, 4 GB de RAM e dois processadores lógicos reconhecidos pelo Windows. A instalação e os testes usam o token comum do usuário, com Secure Boot e Defender em funcionamento. Não foram instalados FFmpeg, Office, Tesseract ou um redistribuível Visual C++ global para ajudar o aplicativo.

O instalador do [build por fontes 2655984](https://github.com/GenissonEmilio/citrica/actions/runs/40605616875) foi instalado em `Aplicação João/Citrica`. A matriz executou a CLI instalada com PATH reduzido ao sistema: **304 conversões de 50 extensões**, **23 operações de áudio/vídeo** e ocultação efetiva de texto por OCR. Os arquivos originais foram preservados. O [relatório completo](evidence/0.6.0/citrica-windows-vm-engine-parity.json) registra cada entrada e saída.

O [teste nativo entre processos Qt/OLE](evidence/0.6.0/citrica-windows-native-validation.json) passou por Shift global, arraste, conversão, atalho, Esc e reabertura vazia. O [Explorer real](evidence/0.6.0/citrica-windows-explorer-1-bundled-validation.json) passou por Ctrl parado, Alt, DOCX→PDF e PDF→DOCX, além de exemplos de imagem, vídeo, áudio, ODT, XLSX, PPTX, legenda e arquivo compactado. Nesse relatório, o nome histórico `docx_pdf_without_office` significa sem Office instalado à parte; `office_engine: bundled` registra o motor incluído no pacote.

QR também foi decodificado pela CLI instalada, com comparação exata do conteúdo e caminho com acentos. Um teste adicional encontrou falha de rostos no diretório de instalação com acentos: o OpenCV tentava abrir o XML por uma API de caminho estreito. O modelo passou a ser lido em memória pelo Python. Os seis testes dessa correção passaram no Windows. Um executável reconstruído na própria VM com o código ff90885 e motores anteriores verificados por SHA-256 passou pelas **38 operações de imagem/PDF**, incluindo rostos, OCR, QR, metadados e recusa de entradas inválidas. Esse build privado não é o instalador final do CI, cuja atualização ainda está em andamento.

Dez sessões adicionais do código-fonte passaram por 40 gestos no Explorer, alternando pastas separadas e a mesma pasta. O Python de QA e seus filhos carregaram seu próprio runtime privado; esse ajuste não foi instalado no sistema nem aplicado aos executáveis congelados. O executável reconstruído passou depois por mais **13 sessões e 52 gestos**, incluindo escala Qt de 150% e três sessões com logging padrão, sem watchdog. O travamento Alt não foi reproduzido nessas sessões.

O [CI 40725014510](https://github.com/GenissonEmilio/citrica/actions/runs/40725014510) passou pela matriz, smoke, instalação, atualização e remoção, mas falhou na ativação Alt do Explorer. O [CI seguinte, 40735116402](https://github.com/GenissonEmilio/citrica/actions/runs/40735116402), passou pela matriz, instalação em caminho com acentos e Explorer básico em escalas de 100% e 150%, mas o residente encerrou com acesso inválido à memória (`0xC0000005`) durante o percurso de todas as famílias. Nenhum dos dois workflows está aprovado como um todo.

Um experimento separado isolou uma falha do diagnóstico periódico no CPython 3.12.10: **três controles encerraram normalmente; três processos com snapshots assíncronos encerraram com `0xC0000005` em menos de 0,3 segundo**. O experimento usa Qt/threads e trabalho em memória, sem importar o Cítrica, injetar entrada ou converter arquivos. [Comparação completa](evidence/0.6.0/windows-python312-watchdog-comparison.json) e [reprodutor](evidence/0.6.0/qa-watchdog-repro.py). A [issue primária do CPython](https://github.com/python/cpython/issues/116008#issuecomment-2034190548) descreve a leitura concorrente dos frames pelo dumper. O snapshot periódico foi removido; a captura fatal opt-in e os eventos OLE permanecem. Novos percursos completos do pacote continuam necessários para encerrar a investigação.

O instalador ff90885 também foi atualizado na VM como usuário comum: preservou preferências/entrada de inicialização, removeu arquivos antigos e teve **19.578 arquivos de motores verificados por SHA-256**. [Recibo da atualização](evidence/0.6.0/citrica-windows-vm-final-upgrade.json).

## Ubuntu e GNOME

O DEB foi instalado, aberto como usuário comum e removido em containers limpos Ubuntu **24.04, 26.04 e 26.10**, incluindo a primeira configuração e PNG→PDF→DOCX. O menu usa o executável nativo mesmo quando existe um portátil antigo antes dele no PATH.

O DEB final do CI ff90885 também passou por **38 operações avançadas como usuário comum no Ubuntu 26.10**, após instalação: imagens, PDFs, rostos, OCR e QR, com cinco paletas exatas e originais preservados. O SHA-256 do DEB é `1e722fb36376c2a6086e7e4e4dadd463813c9c6a07f23aa4872429058ecb03f6`.

Compositores GNOME/Wayland reais e isolados validaram a roda no GNOME 46 e 51 do Ubuntu. GNOME 50 foi validado separadamente no Fedora com o backend congelado do Ubuntu 24.04, incluindo nove quadros intermediários de animação. Os containers Ubuntu desativaram animações por renderização em software; não se atribui a eles a medição de fluidez. [Escopo e recibos Ubuntu](validation-0.6.0-ubuntu.json).

## Confiança do instalador

O instalador 0.5.0, com marcador de origem da Internet, exibiu o aviso de arquivo com fornecedor desconhecido na VM. A tela azul específica do SmartScreen relatada nos PCs externos não foi reproduzida. Os candidatos continuam sem assinatura; não há alegação de que o aviso foi eliminado.

A preparação de Authenticode verifica assinaturas e timestamp, mas uma identidade aprovada ainda depende do mantenedor. A Store oferece um caminho gratuito de cadastro individual e assinatura de MSIX; a SignPath Foundation avalia projetos abertos elegíveis. [Requisitos e links oficiais](WINDOWS-SIGNING.md). Nenhuma proteção do Windows foi desativada e não foi criado certificado autoassinado para simular confiança pública.

Os [resultados estruturados Windows](validation-0.6.0-windows.json) distinguem o pacote inicialmente testado, regressões encontradas e verificações ainda pendentes. A VM e o CI não representam todos os computadores ou documentos.
