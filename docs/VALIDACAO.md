# Validação da versão 0.5.0

A atualização atual é acompanhada em [Validação 0.7.0](VALIDACAO-0.7.0.md). O histórico [0.6.0](VALIDACAO-0.6.0.md) inclui VM Windows 11, motores offline e Ubuntu.

A 0.5.0 trata os relatos de roda ausente/vazia no Windows e inclui PDF→DOCX em ambas as plataformas. O vídeo recebido mostra uma roda sem seleção; arquivos e dados pessoais desse vídeo não fazem parte das evidências públicas.

## Motor compartilhado

PDF→DOCX usa pdf2docx 0.5.13 num subprocesso cancelável. Há testes de texto editável, duas páginas, imagem incorporada, tabela, preservação do original, colisão de nomes, arquivo corrompido, senha e cancelamento sem saída parcial. DOCX→PDF/TXT e TXT→DOCX têm testes reais com o LibreOffice desabilitado, incluindo Unicode, tabela e imagem.

O modo automático prefere LibreOffice para DOCX quando instalado. Sem ele, PDF e TXT são oferecidos e executados pelo motor incluído. O layout básico pode diferir do Word. PDFs escaneados não recebem OCR automático.

## Windows

A prévia roda num subprocesso separado, com prazo de 2,5 segundos, para que uma chamada COM ao Explorer não bloqueie a interface Qt. A prévia lê somente a seleção da janela Explorer que iniciou o gesto. Ela não autoriza converter/mover/copiar: a oferta real OLE confirma os arquivos. FileNameW/CF_HDROP complementam URLs do Qt. A janela não é remapeada ao revelar um probe; um drop válido espera a paleta assíncrona terminar de carregar.

A suíte Qt cobre oferta nativa UTF-16, prévia sem autorização de ação, drop rápido com motor atrasado, DOCX/PDF sem LibreOffice e repetição dos modificadores. O teste Win32 cobre conflito/registro real do atalho.

`tests/windows/explorer_flow.py` abre o Explorer do runner, seleciona arquivos de teste por COM, encontra seus ícones por UI Automation e arrasta com SendInput. Pressiona Ctrl com o mouse parado, testa ações/Alt, DOCX→PDF e PDF→DOCX sem Office, em processos separados do executável empacotado. Executa com escala Qt padrão e QT_SCALE_FACTOR=1.5. Essa escala adicional exercita coordenadas Qt; não representa uma mudança da configuração física de DPI do Windows nem todos os monitores.

O teste anterior entre dois clientes Qt/OLE permanece em `native_flow.py`. O instalador é instalado, aberto e desinstalado no usuário do runner. As evidências do CI devem ser consultadas antes de considerar cada percurso aprovado.

## Linux / Fedora

A extensão GNOME versão 3/revisão 2 mantém a miniatura nativa acima da roda. `run_stacking.py` compara pixels da miniatura em Ctrl/Alt/Shift durante um arraste Wayland real; o percurso do Nautilus confere sua própria miniatura. Os percursos de conversão, atalho, cancelamento, copiar/colar, configurações e animação continuam em `run_all.py`.

```bash
python tests/desktop/run_session.py tests/desktop/run_all.py
CITRICA_TEST_EXECUTABLE=/caminho/citrica python tests/desktop/run_session.py tests/desktop/run_all.py
```

Testes GNOME usam outro compositor com configurações e barramento DBus isolados, sem enviar eventos à sessão do usuário.

## Resultados desta versão

A [candidata empacotada 1d43371](https://github.com/GenissonEmilio/citrica/actions/runs/40420617748) passou em Linux e Windows. Foram **110 testes aprovados e um pulado em cada plataforma**: registro Win32 é exclusivo do Windows; o teste opcional LibreOffice é pulado no runner Windows sem Office. Lint aprovado.

No Windows, passaram o motor congelado, arraste OLE entre processos, atalho global, reabertura vazia, instalação/execução/desinstalação e os quatro percursos pelo Explorer em ambas as escalas Qt: Ctrl parado, DOCX→PDF, PDF→DOCX editável e Alt. As capturas mostram a miniatura do arraste acima da roda. Os relatórios `citrica-windows-*-validation.json` acompanham os pacotes.

A [regressão com arquivos na mesma pasta](https://github.com/GenissonEmilio/citrica/actions/runs/40421599448) passou pelo código-fonte e pelo [pacote Windows final 7239105](https://github.com/GenissonEmilio/citrica/actions/runs/40421603440/job/121917137108), incluindo as conversões consecutivas enquanto o Explorer atualiza a lista de arquivos.

No Fedora, a suíte GNOME completa passou tanto pelo código-fonte quanto pelo executável local congelado em 07a7226. Após as correções exclusivas do Windows, o executável reconstruído em 3c82736 passou novamente pelos percursos PDF→DOCX e miniatura em Ctrl/Alt/Shift. A comparação da miniatura teve erro de pixels **0,0** nos três modos. A captura de animação registrou **14 quadros intermediários** na abertura.

A instalação deste usuário foi atualizada para 0.5.0 e passou pelo smoke do executável instalado: imagens, PDF multipágina, PDF→DOCX editável, DOCX→PDF/TXT sem Office e ferramentas. A extensão revisão 2 já está ativa, sem exigir nova sessão. Esse pacote foi construído no Fedora; os downloads públicos são construídos pelo CI Ubuntu/Windows.

Os resultados estruturados estão em [validation.json](validation.json). O teste nos PCs dos usuários Windows continua a cargo dos validadores externos; a automação não representa todos os documentos ou ambientes.

A validação anterior da 0.4.0 está preservada em [VALIDACAO-0.4.0.md](VALIDACAO-0.4.0.md).
