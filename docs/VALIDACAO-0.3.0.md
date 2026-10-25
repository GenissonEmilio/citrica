# Validação da versão 0.3.0

Ambiente desktop: Fedora 44, GNOME Shell 50.5, Mutter 50.6, Wayland, x86_64. Validação realizada em 25/10/2026 (horário de Fortaleza). O teste usa outro compositor GNOME real com monitor virtual, barramento DBus e configurações isolados. Não é uma simulação web e não injeta eventos na sessão de trabalho do usuário.

## Percurso do desktop

`tests/desktop/run_session.py` inicia o Shell, carrega a extensão de produção e um harness de teste, abre um cliente Wayland Qt com arquivo local e executa `run_flow.py`. São verificados:

- Nenhuma roda antes da tecla durante um arraste de arquivo real.
- Shift global abre os formatos; soltar Shift mantém a roda aberta.
- Movimento seleciona o setor JPG; soltar o mouse publica uma imagem JPG real, sem erro.
- Super+Shift+C abre a roda sem arraste; Escape fecha mesmo com foco em outro aplicativo.
- Opacidade/escala reais variam durante a abertura de 240 ms e chegam ao estado final.
- Alt abre ferramentas durante um novo arraste; Ctrl troca para ações.
- Soltar em Copiar caminho altera o clipboard do compositor de teste para o caminho exato.
- Mais troca a página de ferramentas; Recortar abre somente o diálogo específico.
- Escape durante um arraste cancela sem publicar outra conversão.
- Alterar o modificador para Super e o atalho para Super+Shift+V tem efeito no Shell; ao final, restaura Shift e Super+Shift+C.
- Setas/Enter convertem pelo teclado, sem perder seleção no polling do ponteiro; desativar animações aplica opacidade/escala finais imediatamente.

O harness fornece dispositivos virtuais somente ao compositor de teste, nunca é instalado na sessão normal nem incluído no pacote. O teste não altera unsafe_mode, portais ou permissões do GNOME. Comandos reproduzíveis:

~~~bash
python tests/desktop/run_session.py
# Interoperabilidade com o Nautilus real:
python tests/desktop/run_session.py tests/desktop/run_nautilus.py
# Resultados: build/desktop-test/result.json, shell.log e imagens PNG
~~~

![Setor escolhido durante um arraste](wheel.png)

O segundo teste abre o Nautilus numa pasta de fixtures do compositor isolado. Inicia o arraste do PNG, pressiona Shift, escolhe JPG e solta. Confere a cópia JPG de 320 × 200 pixels, o original presente e zero erros no motor. Resultado em build/desktop-test/nautilus-result.json.

Também copia um arquivo pelo setor Copiar e cola numa segunda janela do Nautilus, comparando seu conteúdo. `run_actions.py` abre um terminal pela roda, executa pwd somente nesse terminal de teste e confere a pasta; depois arrasta o arquivo a partir da prateleira, abre a roda e cancela. Todos esses percursos passaram.

~~~bash
python tests/desktop/run_session.py tests/desktop/run_actions.py
python tests/desktop/run_session.py tests/desktop/run_settings.py
~~~

## Motor e diálogos

A suíte pytest concluiu **88 testes**, sem falhas (um aviso de depreciação da API de evento Qt usada no teste legado). Exercita conversões reais, preservação dos originais, colisões concorrentes, arquivos inseguros recusados, cancelamento, documentos Office, PDF multipágina, mídia, arraste Qt e recorte visual até o arquivo salvo. A prévia HEIC e a orientação EXIF também são verificadas. Mover é testado com um destino que já contém um arquivo de mesmo nome; ambos os conteúdos são preservados, e Esc durante o trabalho solicita cancelamento sem destruir a thread ativa.

Todas as 26 entradas do catálogo de ferramentas têm execução real coberta nos testes de motor. Os testes conferem dimensões, páginas, duração/canais, pixels, metadados ou limites de bytes conforme a operação. Há casos positivos com imagem NASA para rosto, texto gerado localmente para Tesseract e QR gerado nos testes. Não se usa apenas uma lista simulada de capacidades.

A validação de atalho recusa tecla inválida, sequências com mais de uma tecla, modificadores repetidos, Shift isolado e conflito registrado no GNOME, inclusive quando a ordem dos modificadores difere. O teste run_settings.py digita Super+F8 na janela real, salva, confirma a preferência no Shell e invoca a roda com esse novo atalho; ao terminar, restaura Super+Shift+C.

No CI Ubuntu 24.04, `packaging/build.py` testa o executável congelado por subprocessos: JPG, HEIC, AVIF, PDF, renderização de todas as páginas, detecção de rostos/texto e fundo. O pacote somente é publicado depois desses testes e da abertura das configurações em modo offscreen. O CI não executa o compositor GNOME 50: essa evidência é local no Fedora.

## Escopo e limites em relação ao Tangerine

| Pedido/referência | Resultado no Cítrica | Limite verificável |
| --- | --- | --- |
| Roda durante arraste + Shift | Extensão GNOME 50/Wayland com animação e resultado junto da origem | Outros compositores/versões não validados |
| Ferramentas por modificador | Alt; 26 entradas implementadas | Algoritmos e todos os controles não são idênticos ao comercial |
| Ações por modificador | Ctrl; copiar, mover, caminho, terminal e prateleira | Pastas grandes e gerenciadores de arquivos adicionais precisam de validação |
| AirDrop | Integração opcional LocalSend | AirDrop não implementado; LocalSend não instalado no ambiente de validação, envio entre máquinas não validado |
| Ocultar rosto/texto | OpenCV Haar e Tesseract locais + ocultação manual | Detecção pode falhar; inglês incluído, revisão necessária |
| Tamanho em bytes/percentual | Imagem/PDF/áudio/vídeo; publica só se respeitar limite | Pode recusar limite muito baixo; imagem pode perder resolução |
| Edição e organização | Recorte, ajuste, anotações, fundos, mídia e PDF | Não é um editor completo; união de mídia exige entradas compatíveis |
| Metadados | Leitura, autor/título e remoção de tags nos tipos indicados | Não remove tags de documentos Office nem garante ausência de toda informação identificável |
| 275 opções comerciais | Tabela explícita de conversões no README | Sem SVG/RAR/Pages/EPUB/PDF→Office e sem equivalência numérica declarada |

O teste automatizado cobre o fluxo e os motores com fixtures controlados. Não representa teste de todos os documentos, todos os codecs, todas as configurações de hardware ou todas as combinações de aplicativos. O estado da extensão na sessão do usuário é consultado separadamente; atualizações de código entram em vigor no próximo login do GNOME.

## Regressões e visual da 0.3.0

`run_regressions.py` converte duas vezes, tenta uma imagem inválida, cancela com Escape e reabre pelo atalho depois de cada caso. Confere caminhos vazios, ausência de opções/miniatura/destaque e cache descartado. Um wrapper de teste atrasa o motor real: respostas que chegam depois de fechar, substituir por roda vazia ou terminar o arraste não podem restaurar a seleção anterior.

`run_visual.py` grava a saída do compositor de teste pelo gravador nativo do GNOME e observa estados em eventos de pintura do stage. Confere vários quadros intermediários de escala/opacidade durante a abertura e o estado final. A gravação não é uma maquete nem uma sequência de imagens geradas. As durações configuradas são 240 ms na abertura, 230 ms nos setores com defasagem de 8 ms, 140 ms no hover e 130 ms ao fechar. Isso não promete uma taxa fixa de quadros em todo hardware.

[Gravação nativa da roda](wheel-native.mp4) · [Comparação com a referência](ANALISE.md)

Para executar todos os percursos no mesmo compositor isolado:

~~~bash
python tests/desktop/run_session.py tests/desktop/run_all.py
# Para testar um pacote, mantendo as entradas e a extensão de teste isoladas:
CITRICA_TEST_EXECUTABLE=/caminho/absoluto/citrica/citrica python tests/desktop/run_session.py tests/desktop/run_all.py
~~~

A prévia recebe testes de orientação EXIF, proporção, limite de 128 px, reutilização/invalidação do cache, original intacto e seleção vazia/múltipla sem miniatura antiga. Uma falha de prévia não remove os formatos válidos.

## Portátil da release no Fedora

O portátil produzido pelo [CI 40193324649](https://github.com/GenissonEmilio/citrica/actions/runs/40193324649), commit 061c730, foi baixado e conferido com SHA256SUMS. Os arquivos extension.js, wheel.js e metadata.json incluídos no pacote são idênticos aos usados pelo compositor de teste. O executável congelado passou no Fedora em:

- Conversões JPG, HEIC, AVIF, PDF, renderização multipágina, detecção de rostos/texto, fundo, FFmpeg/ffprobe e Office.
- Todos os percursos de `run_all.py`: arraste Qt e Nautilus, conversão, copiar/colar, terminal, prateleira, configurações, atalhos, regressões de seleção e captura da animação.
- Repetição de sucesso, erro, cancelamento e respostas atrasadas, com reabertura vazia pelo atalho.

O pacote foi instalado no usuário com o comando `citrica`, menu do aplicativo e Super+Shift+C. A revisão nativa instalada é versão 3, revisão 1. Na consulta após instalar, a sessão principal ainda executava versão 2 sem revisão e, portanto, **a roda nova ainda não estava ativa nessa sessão**. As configurações mostram essa pendência. O GNOME 50 mantém o módulo importado em memória e exige novo login para trocar a versão; não foi encerrada a sessão de trabalho do usuário.

Resultados, checksum e distinção entre revisão instalada e carregada estão em [validation-0.3.0.json](validation-0.3.0.json). As capturas desta documentação foram atualizadas com o percurso do executável empacotado no compositor isolado.
