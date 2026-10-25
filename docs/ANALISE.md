# Do Tangerine ao Cítrica no Linux

Referências analisadas em 24 de outubro de 2026:

- [Tangerine na App Store](https://apps.apple.com/es/app/tangerine-file-converter/id6813034065?mt=12), com descrição também verificada pela API pública da Apple.
- [Reel de rensenlabs](https://www.instagram.com/reel/DezqwzuGx6T/), acessado pelo navegador: apresenta arrastar, pressionar Shift e soltar para converter, com processamento offline.
- [Site e demonstração oficial](https://www.tangerineformac.com/) e [press kit](https://www.tangerineformac.com/press).

A proposta central observada é reduzir a interrupção do trabalho: o formato aparece perto do arquivo, os menus dependem do tipo selecionado e o resultado fica junto da origem. O produto comercial também anuncia ferramentas de edição, ações sobre arquivos e lotes. Esta implementação reproduz o fluxo essencial com identidade própria, sem reutilizar código ou recursos do Tangerine. Não é uma reprodução completa das ferramentas anunciadas pelo produto comercial.

## Decisões para Linux

**Qt Widgets / PySide6:** interface desktop, suporte a arrastar/soltar, teclado, X11 e Wayland. O motor funciona também sem interface via CLI. Pillow e pillow-heif tratam imagens; pypdf e PyMuPDF tratam PDF; FFmpeg e LibreOffice ampliam formatos com ferramentas já conhecidas no ecossistema Linux.

**Um gesto adaptado:** não há uma API universal que permita observar o arraste e pressionamentos globais de outros aplicativos no Wayland. A prévia usa uma janela flutuante receptora de arquivos e integrações por gerenciador. O usuário arrasta até o círculo, escolhe a saída e solta. Um atalho personalizado do desktop pode chamar `citrica --dock`. Uma integração futura específica com GNOME/KDE deve passar pelas permissões e APIs do compositor correspondente.

**Original preservado:** a saída é criada em área temporária na pasta de destino. O commit usa criação atômica sem sobrescrita; colisões geram um nome novo, inclusive quando duas operações terminam simultaneamente. Um PDF renderizado produz todas as páginas. Imagens animadas são recusadas até haver exportação que preserve seus quadros.

**Escopo verificável:** a prévia não anuncia centenas de combinações ou equivalência com todas as funções comerciais. A tabela no README indica os recursos implementados e suas dependências. Os formatos são filtrados pela disponibilidade de motores; codecs individuais do FFmpeg ainda podem variar conforme a instalação.

## Evolução

A prioridade seguinte é validar arrastar/soltar entre aplicações reais em GNOME/Wayland e KDE, depois avaliar uma extensão de desktop para aproximação do gesto global. O menu radial e o motor de conversão permanecem independentes dessa futura integração.
