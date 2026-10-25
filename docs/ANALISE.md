# Do Tangerine ao Cítrica no Linux

Referências: [App Store](https://apps.apple.com/es/app/tangerine-file-converter/id6813034065?mt=12), [reel fornecido](https://www.instagram.com/reel/DezqwzuGx6T/), [site oficial](https://www.tangerineformac.com/) e [press kit](https://www.tangerineformac.com/press), consultados em 24/10/2026.

O fluxo central é iniciar um arraste, tocar Shift e soltar num formato próximo do ponteiro. A roda permanece depois de soltar a tecla. Command abre ferramentas no Mac e Control abre ações. O site anuncia 26 ferramentas, 6 ações e 275 opções de conversão. Esses números descrevem o produto de referência, não uma equivalência validada do Cítrica.

A versão 0.1.0 tinha uma janela grande e uma área flutuante. Isso interrompia o fluxo e não atendia à experiência solicitada. A versão 0.2.0 substitui a entrada principal por uma extensão nativa do GNOME 50. Qt fica responsável pelas configurações e pelos diálogos de ferramentas. O motor continua independente e acessível pela CLI.

## Integração com o compositor

Um cliente Wayland comum não observa o arraste de outro aplicativo. A extensão usa a seleção DND do Mutter e o estado global do ponteiro/modificadores dentro do GNOME Shell, sem desativar as restrições de segurança do Shell. A roda é um ator St na camada de chrome, com abertura animada de 180 ms, sem janela decorada. O polling ocorre apenas durante arrastes ou com a roda aberta.

Shift abre conversões, Alt substitui o Command para ferramentas, Ctrl abre ações. Super+Shift+C é o atalho padrão, configurável. Escape cancela; setas/Enter navegam. O conteúdo é consultado no motor local, que filtra operações pela seleção e dependências. O Shell recebe caminhos de arquivos locais, não executa texto extraído dos arquivos.

A implementação é específica de GNOME 50. KDE e outras versões de GNOME precisam de integração e validação próprias. Novas extensões/atualizações precisam ser carregadas pelo Shell numa nova sessão.

## Integridade e ferramentas

Conversões usam staging na pasta de destino e publicação atômica sem sobrescrita. Ferramentas produzem cópias; somente a ação explícita Mover remove a origem depois de publicar a cópia no destino. Imagens com orientação EXIF são apresentadas e processadas na mesma orientação.

O catálogo implementa operações de imagem, PDF, áudio e vídeo, incluindo detecção local de regiões de rosto/texto e compressão por tamanho. A qualidade visual e a detecção não são declaradas equivalentes aos algoritmos comerciais. AirDrop não é oferecido; LocalSend é uma integração opcional. Limites e provas estão em [VALIDACAO.md](VALIDACAO.md).
