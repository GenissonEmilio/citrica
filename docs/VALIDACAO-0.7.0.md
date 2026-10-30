# Validação do Cítrica 0.7.0

Produto 0.7.0; pacote Microsoft Store 1.7.0.0; protocolo GNOME 3, revisão 4. Este documento acompanha os resultados da atualização. O histórico anterior permanece em [0.6.0](VALIDACAO-0.6.0.md).

## Escopo

- Cinco estilos compartilhados entre Qt e GNOME, persistência das preferências e migração sem redefinir atalhos.
- Editores visuais de imagem/PDF e player/linha do tempo de áudio/vídeo, exportações reais e cancelamento.
- Detecção LocalSend Linux nativa/Flatpak/AppImage e encaminhamento dos arquivos.
- Cancelamento do arraste Windows: fora do anel, centro vazio, oferta OLE atrasada, soltura não notificada e novo gesto depois de Mais.
- Pacotes completos Linux/Windows e atualização MSIX com identidade preservada.

## Resultados em código-fonte

O teste GNOME 50/Wayland em compositor isolado trocou os cinco estilos durante um arraste real, preservou arquivo, opções e miniatura, converteu para JPG e reabriu a roda vazia. O recibo da revisão 4 registra 14 quadros intermediários de animação. Esse teste não reiniciou nem substituiu a extensão na sessão de trabalho do usuário.

No Fedora, a detecção real encontrou LocalSend 1.18.2 instalado como Flatpak de sistema (`org.localsend.localsend_app`), sem executável no PATH. A paleta do protocolo passou a incluir Compartilhar. Os testes verificam `--file-forwarding` com nomes Unicode e espaços; não iniciam transferências reais.

Os testes dos editores exportam recortes e ajustes de imagem, fundo com proporção, PDF reordenado, trim de vídeo e bleep de áudio. Também exercitam alças/arraste, sincronização dos campos, miniaturas, forma de onda, reprodução/pausa/seek no QtMultimedia e cancelamento seguro de subprocessos e workers.

## Pacotes e publicação

Builds, testes da VM Windows, pacotes Ubuntu e envio à Store ainda estão em preparação nesta branch. Resultados de código-fonte ou de uma versão anterior não são tratados como aprovação dos pacotes novos. Os recibos serão acrescentados conforme cada etapa terminar.

## Limites

Os estilos translúcidos usam alpha real; não aplicam blur ao desktop. Há prévia do primeiro arquivo em operações múltiplas. As ferramentas são editores focados: não há montagem multipista, transições ou editor completo de Office. O player depende dos codecs do Qt; miniaturas e quadros por FFmpeg servem de alternativa quando suportados. A exportação usa os motores de conversão próprios e pode exigir FFmpeg/LibreOffice no Linux.

LocalSend em instalação Flatpak customizada por nome não é descoberto automaticamente. AppImages precisam ter permissão de execução e estar em pastas usuais ou em um launcher seguro. A ação abre o aplicativo com os arquivos; o usuário conclui o envio no LocalSend.

GitHub EXE/ZIP continuam sem assinatura pública. O MSIX oficial é preparado separadamente para certificação e assinatura da Microsoft Store; um pacote QA local não demonstra instalação pela Store.
