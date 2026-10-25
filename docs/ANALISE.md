# Do Tangerine ao Cítrica no Linux

Referências: [App Store](https://apps.apple.com/es/app/tangerine-file-converter/id6813034065?mt=12), [reel fornecido](https://www.instagram.com/reel/DezqwzuGx6T/), [site oficial](https://www.tangerineformac.com/) e [press kit](https://www.tangerineformac.com/press), consultados em 24–25/10/2026. Na revisão visual, o Instagram limitou o acesso; a observação quadro a quadro foi feita no vídeo de demonstração oficial, reproduzido no navegador, e nas capturas do press kit.

O fluxo central é iniciar um arraste, tocar Shift e soltar num formato próximo do ponteiro. A roda permanece depois de soltar a tecla. Command abre ferramentas no Mac e Control abre ações. O site anuncia 26 ferramentas, 6 ações e 275 opções de conversão. Esses números descrevem o produto de referência, não uma equivalência validada do Cítrica.

A versão 0.1.0 tinha uma janela grande e uma área flutuante. A 0.2.0 adotou uma extensão nativa, mas desenhou um disco escuro com botões separados e conservava a seleção em revisões antigas. A 0.3.0 corrige o ciclo de seleção e redesenha a roda a partir da análise visual abaixo. Qt fica responsável pelas configurações e pelos diálogos específicos. O motor continua independente e acessível pela CLI.

## Análise visual e movimento

O vídeo oficial mostra a ativação perto de 1,35 s e o anel aberto perto de 1,575 s. Perto de 2,925 s, MP3 aparece destacado. A diferença determinante é a construção: setores anulares claros, separados por espaços estreitos, com cantos arredondados; arquivo no centro transparente e uma pequena cápsula de tamanho/ação. As ferramentas usam ícones acima dos rótulos. O zoom da câmera do vídeo não foi interpretado como expansão do setor selecionado.

| Elemento observado | Implementação na 0.3.0 |
| --- | --- |
| Anel pêssego/creme, sem disco escuro | Setores vetoriais Cairo independentes, raio externo 170 px, interno 66 px, intervalos e cantos arredondados |
| Arquivo no centro e cápsula | Miniatura local limitada a 128 px, exibida a 64 px; tamanho inicial e nome da operação sob o ponteiro |
| Setor laranja sob o arraste | Gradiente laranja, transição de opacidade de 110 ms e deslocamento radial de 4 px em 140 ms |
| Abertura rápida e elástica | Escala/opacidade de 240 ms; setores com expansão elástica de 230 ms, defasagem de 8 ms |
| Troca de ferramentas sem outra janela | Conteúdo anterior desvanece em 90 ms; Alt/Ctrl usam a mesma roda |
| Saída suave | Fechamento em 130 ms; os dados da seleção já são apagados antes da animação |

Os desenhos são próprios, renderizados no compositor. Nenhum arquivo visual do produto comercial foi incluído. As durações são escolhas de implementação baseadas na observação, não medições internas do Tangerine. A animação usa transformações do compositor; os setores não são redesenhados pela CPU a cada quadro. As capacidades são antecipadas ao iniciar o arraste para que Shift possa abrir a roda com conteúdo pronto.

O estado vazio tem setores discretos e convite para arrastar/escolher, sem sugerir que existe um arquivo selecionado. Fechar invalida respostas assíncronas pendentes, limpa caminhos, formatos, miniatura, destaque e cache do arraste. O atalho só aproveita caminhos quando há um arraste realmente ativo com o botão pressionado.

## Integração com o compositor

Um cliente Wayland comum não observa o arraste de outro aplicativo. A extensão usa a seleção DND do Mutter e o estado global do ponteiro/modificadores dentro do GNOME Shell, sem desativar as restrições de segurança do Shell. A roda é um ator St na camada de chrome, sem janela decorada. O polling ocorre apenas durante arrastes ou com a roda aberta.

Shift abre conversões, Alt substitui o Command para ferramentas, Ctrl abre ações. Super+Shift+C é o atalho padrão, configurável. Escape cancela; setas/Enter navegam. O conteúdo é consultado no motor local, que filtra operações pela seleção e dependências. O Shell recebe caminhos de arquivos locais, não executa texto extraído dos arquivos.

A implementação é específica de GNOME 50. KDE e outras versões de GNOME precisam de integração e validação próprias. Novas extensões/atualizações precisam ser carregadas pelo Shell numa nova sessão.

## Integridade e ferramentas

Conversões usam staging na pasta de destino e publicação atômica sem sobrescrita. Ferramentas produzem cópias; somente a ação explícita Mover remove a origem depois de publicar a cópia no destino. Imagens com orientação EXIF são apresentadas e processadas na mesma orientação.

O catálogo implementa operações de imagem, PDF, áudio e vídeo, incluindo detecção local de regiões de rosto/texto e compressão por tamanho. A qualidade visual e a detecção não são declaradas equivalentes aos algoritmos comerciais. AirDrop não é oferecido; LocalSend é uma integração opcional. Limites e provas estão em [VALIDACAO.md](VALIDACAO.md).

## Windows na versão 0.4.0

A integração Windows reutiliza o motor e os diálogos de ferramentas, com uma roda Qt própria que reproduz a geometria, paleta e movimento descritos nesta análise. O aplicativo permanece na bandeja. RegisterHotKey fornece o atalho configurável; uma oferta OLE de arquivos locais valida o arraste antes de revelar a roda. O efeito de cópia preserva a origem, inclusive com Shift pressionado.

As capacidades e conversões executam em workers, com resultados entregues à thread da interface. Aberturas adicionais usam um named pipe restrito ao usuário. O pacote inclui inicializadores gráfico e CLI, instalador no usuário e opção portátil. O guia e os limites estão em [WINDOWS.md](WINDOWS.md); os testes nativos e o teste externo ainda pendente estão em [VALIDACAO.md](VALIDACAO.md).
