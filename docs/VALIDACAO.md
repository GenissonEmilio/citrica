# Validação da versão 0.5.0

A 0.5.0 trata os relatos de roda ausente/vazia no Windows e inclui PDF→DOCX em ambas as plataformas. O vídeo recebido mostra uma roda sem seleção; arquivos e dados pessoais desse vídeo não fazem parte das evidências públicas.

## Motor compartilhado

PDF→DOCX usa pdf2docx 0.5.13 num subprocesso cancelável. Há testes de texto editável, duas páginas, imagem incorporada, tabela, preservação do original, colisão de nomes, arquivo corrompido, senha e cancelamento sem saída parcial. DOCX→PDF/TXT e TXT→DOCX têm testes reais com o LibreOffice desabilitado, incluindo Unicode, tabela e imagem.

O modo automático prefere LibreOffice para DOCX quando instalado. Sem ele, PDF e TXT são oferecidos e executados pelo motor incluído. O layout básico pode diferir do Word. PDFs escaneados não recebem OCR automático.

## Windows

A prévia lê somente a seleção da janela Explorer que iniciou o gesto. Ela não autoriza converter/mover/copiar: a oferta real OLE confirma os arquivos. FileNameW/CF_HDROP complementam URLs do Qt. A janela não é remapeada ao revelar um probe; um drop válido espera a paleta assíncrona terminar de carregar.

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

Validação da candidata em execução. Os relatórios finais e as referências dos builds serão registrados aqui e em `validation.json` antes da publicação.

A validação anterior da 0.4.0 está preservada em [VALIDACAO-0.4.0.md](VALIDACAO-0.4.0.md).
