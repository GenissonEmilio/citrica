# Validação da candidata 0.6.0

A candidata inclui os motores de conversão no Windows e corrige a instalação do DEB e a integração com GNOME 46/50/51. Ainda não é uma release pública assinada. O histórico da versão pública permanece em [VALIDACAO.md](VALIDACAO.md).

## Windows 11 em máquina virtual

Foi usada uma VM separada com Windows 11 Pro x64 em português, build 26300.9457, 4 GB de RAM e dois processadores lógicos reconhecidos pelo Windows. A instalação e os testes usam o token comum do usuário, com Secure Boot e Defender em funcionamento. Não foram instalados FFmpeg, Office, Tesseract ou um redistribuível Visual C++ global para ajudar o aplicativo.

O instalador do [build por fontes 2655984](https://github.com/GenissonEmilio/citrica/actions/runs/40605616875) foi instalado em `Aplicação João/Citrica`. A matriz executou a CLI instalada com PATH reduzido ao sistema: **304 conversões de 50 extensões**, **23 operações de áudio/vídeo** e ocultação efetiva de texto por OCR. Os arquivos originais foram preservados. O [relatório completo](evidence/0.6.0/citrica-windows-vm-engine-parity.json) registra cada entrada e saída.

O [teste nativo entre processos Qt/OLE](evidence/0.6.0/citrica-windows-native-validation.json) passou por Shift global, arraste, conversão, atalho, Esc e reabertura vazia. O [Explorer real](evidence/0.6.0/citrica-windows-explorer-1-bundled-validation.json) passou por Ctrl parado, Alt, DOCX→PDF e PDF→DOCX, além de exemplos de imagem, vídeo, áudio, ODT, XLSX, PPTX, legenda e arquivo compactado. Nesse relatório, o nome histórico `docx_pdf_without_office` significa sem Office instalado à parte; `office_engine: bundled` registra o motor incluído no pacote.

QR também foi decodificado pela CLI instalada, com comparação exata do conteúdo e caminho com acentos. Um teste adicional encontrou falha de rostos no diretório de instalação com acentos: o OpenCV tentava abrir o XML por uma API de caminho estreito. O modelo passou a ser lido em memória pelo Python. Os seis testes dessa correção passaram no Windows; a confirmação pelo pacote reconstruído ainda está em andamento.

Dez sessões adicionais do código-fonte passaram por 40 gestos no Explorer, alternando pastas separadas e a mesma pasta. O Python de QA e seus filhos carregaram seu próprio runtime privado; esse ajuste não foi instalado no sistema nem aplicado aos executáveis congelados. O travamento Alt não foi reproduzido nessas sessões.

O [CI 40725014510](https://github.com/GenissonEmilio/citrica/actions/runs/40725014510) passou pela matriz, smoke, instalação, atualização e remoção, mas falhou na ativação Alt do Explorer. Esse workflow não está aprovado como um todo. O residente recebeu diagnóstico opt-in de stacks para investigar a condição intermitente, sem repetir silenciosamente ou ignorar a falha. O [CI seguinte](https://github.com/GenissonEmilio/citrica/actions/runs/40735116402) está em execução.

## Ubuntu e GNOME

O DEB foi instalado, aberto como usuário comum e removido em containers limpos Ubuntu **24.04, 26.04 e 26.10**, incluindo a primeira configuração e PNG→PDF→DOCX. O menu usa o executável nativo mesmo quando existe um portátil antigo antes dele no PATH.

Compositores GNOME/Wayland reais e isolados validaram a roda no GNOME 46 e 51 do Ubuntu. GNOME 50 foi validado separadamente no Fedora com o backend congelado do Ubuntu 24.04, incluindo nove quadros intermediários de animação. Os containers Ubuntu desativaram animações por renderização em software; não se atribui a eles a medição de fluidez. [Escopo e recibos Ubuntu](validation-0.6.0-ubuntu.json).

## Confiança do instalador

O instalador 0.5.0, com marcador de origem da Internet, exibiu o aviso de arquivo com fornecedor desconhecido na VM. A tela azul específica do SmartScreen relatada nos PCs externos não foi reproduzida. Os candidatos continuam sem assinatura; não há alegação de que o aviso foi eliminado.

A preparação de Authenticode verifica assinaturas e timestamp, mas uma identidade aprovada ainda depende do mantenedor. A Store oferece um caminho gratuito de cadastro individual e assinatura de MSIX; a SignPath Foundation avalia projetos abertos elegíveis. [Requisitos e links oficiais](WINDOWS-SIGNING.md). Nenhuma proteção do Windows foi desativada e não foi criado certificado autoassinado para simular confiança pública.

Os [resultados estruturados Windows](validation-0.6.0-windows.json) distinguem o pacote inicialmente testado, regressões encontradas e verificações ainda pendentes. A VM e o CI não representam todos os computadores ou documentos.
