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

O encerramento foi testado em subprocessos independentes: fechar/exportar PDF, sair com worker ativo, capturar com prévia ativa e abrir/fechar cinco PDFs no residente. Threads são canceladas e aguardadas; a árvore de widgets é destruída enquanto o QApplication está vivo. A prévia PDF também foi verificada em três tamanhos de janela, preservando topo, rodapé e proporção.

A suíte completa foi executada três vezes em processos independentes no Fedora: 353 testes passaram e 21 foram ignorados em cada execução, com código de saída 0. O [recibo](evidence/0.7.0/unit-lifecycle.json) distingue esses testes dos pacotes. A limpeza de janelas criadas diretamente pelos testes também foi corrigida; nenhuma assertion foi removida e nenhum erro fatal foi suprimido.

A [verificação final de código-fonte](evidence/0.7.0/source-tests-final.json) passou 356 testes e ignorou 21 em cada plataforma, Linux e Windows, com saída 0. O teste de escala Windows usa o renderizador nativo e fontes Segoe UI: o plugin genérico offscreen não disponibiliza fontes nesse sistema e não representa as métricas do aplicativo. A [prova separada na VM](evidence/0.7.0/windows-settings-dpi-source.json) confirma os cinco estilos e os dois botões de salvar dentro da área útil em 100% e 150%; ela usa código-fonte e não substitui o teste do pacote final.

## Pacotes e publicação

O [build Linux](evidence/0.7.0/linux-packages-ci.json) passou 304 conversões sobre 50 extensões e 38 operações estáticas de imagem/PDF (32 positivas e seis rejeições esperadas), com originais preservados. O DEB passou instalação, abertura, conversão e remoção em Ubuntu 24.04, 26.04 e 26.10 limpos.

O [TAR final no Fedora/GNOME 50](evidence/0.7.0/linux-frozen-gnome.json) passou pelos editores e controles reais, pelas cinco aparências durante o arraste, persistência das preferências, atalho global e presença de Compartilhar. O player avançou 0,557 s durante a reprodução, manteve a posição em pausa, navegou para 1,812 s e exportou um corte de 1,25 s. Todos os processos de editor encerraram com código 0; página PDF inteira e botões de configurações ficaram visíveis em 1280×800. O áudio sintético foi silenciado no teste e não houve envio pelo LocalSend.

A [instalação local](evidence/0.7.0/local-install.json) foi atualizada para esse mesmo binário, com backup e preferências preservadas. A extensão revisão 4 está no disco; a sessão em execução mantém a revisão 2 até o próximo login, sem encerrar o trabalho do usuário.

O pacote Windows e seu MSIX ainda estão em preparação nesta branch. As verificações Linux não são tratadas como validação do Windows nem como certificação da Microsoft.

## Limites

Os estilos translúcidos usam alpha real; não aplicam blur ao desktop. Há prévia do primeiro arquivo em operações múltiplas. As ferramentas são editores focados: não há montagem multipista, transições ou editor completo de Office. O player depende dos codecs do Qt; miniaturas e quadros por FFmpeg servem de alternativa quando suportados. A exportação usa os motores de conversão próprios e pode exigir FFmpeg/LibreOffice no Linux.

LocalSend em instalação Flatpak customizada por nome não é descoberto automaticamente. AppImages precisam ter permissão de execução e estar em pastas usuais ou em um launcher seguro. A ação abre o aplicativo com os arquivos; o usuário conclui o envio no LocalSend.

GitHub EXE/ZIP continuam sem assinatura pública. O MSIX oficial é preparado separadamente para certificação e assinatura da Microsoft Store; um pacote QA local não demonstra instalação pela Store.
