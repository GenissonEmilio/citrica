# Validação da candidata 0.6.0

A parte funcional passou no Windows e no Ubuntu. O pacote Windows continua **sem assinatura pública**; os testes não eliminam o aviso de fornecedor desconhecido. A versão pública estável permanece em 0.5.0 até a conclusão da distribuição assinada.

## Pacote Windows final

O [CI completo 40760249570](https://github.com/GenissonEmilio/citrica/actions/runs/40760249570) passou com o código de produção `8e86d5b`. O instalador testado tem SHA-256:

```text
efc623505e0bd47d4b3c723d53c9ff60d45746e2bb5ba1cc701d703fa64d77bc
```

O CI executou **304 conversões de 50 extensões**, **23 operações de mídia**, **38 operações avançadas de imagem/PDF**, instalação em caminho acentuado, atualização e remoção com o aplicativo aberto, arraste OLE e quatro percursos no Explorer. [Matriz de conversão](evidence/0.6.0/citrica-windows-ci-final-engine-parity.json), [ferramentas](evidence/0.6.0/citrica-windows-ci-final-static-tools-parity.json) e [instalador](evidence/0.6.0/citrica-windows-ci-final-installer-validation.json).

A VM usa Windows 11 Pro x64 em português, build 26300.9457, 4 GB e dois processadores lógicos reconhecidos pelo Windows. Os testes usam o token comum do usuário, com Secure Boot e Defender ativos, sem Office, FFmpeg, Tesseract ou redistribuível Visual C++ global instalado para ajudar o aplicativo. O caminho `Aplicação João/Citrica` contém espaços e acentos; caminhos longos do Windows permanecem desabilitados.

O **mesmo instalador final do CI** passou na VM por:

- [Atualização da versão pública 0.5.0 com seu residente aberto](evidence/0.6.0/citrica-windows-vm-public-05-upgrade.json), preservando preferências e confirmando no log o helper novo.
- [Atualização da instalação anterior](evidence/0.6.0/citrica-windows-vm-release-upgrade.json), com residente aberto, preferências e inicialização preservadas, arquivos obsoletos removidos e **19.578 arquivos de motores conferidos por SHA-256**.
- [38 operações avançadas pela CLI instalada](evidence/0.6.0/citrica-windows-vm-installed-final-static-tools.json), incluindo rostos, OCR, QR, metadados e recusas de entradas inválidas.
- [Quatro sessões e 24 arrastes reais](evidence/0.6.0/citrica-windows-vm-installed-final-summary.json): Ctrl, Alt, Shift, PDF↔DOCX, todas as oito famílias, mesma pasta e escala Qt de 150%. Os originais foram preservados.
- [Recusa de desinstalação sem o helper](evidence/0.6.0/citrica-windows-vm-uninstall-refusal.json): exit code 1, sem remover aplicativo, preferências, entrada de inicialização ou Enviar para.
- [Remoção e reinstalação normais](evidence/0.6.0/citrica-windows-vm-release-uninstall.json), preservando preferências e removendo os atalhos/registro apropriados.

A VM foi deixada ligada com os exemplos sintéticos em **Teste Cítrica**, atalho **Ctrl+Alt+C**, arraste com **Shift** e animações habilitadas. O atalho foi conferido novamente depois de desligar o controlador temporário de QA. [Estado final](evidence/0.6.0/citrica-windows-vm-final-state.json), [limpeza do controlador](evidence/0.6.0/citrica-windows-vm-controller-cleanup.json) e [roda vazia após o atalho](evidence/0.6.0/windows-final-empty-wheel.png).

Uma candidata inicial também executou a matriz completa na VM: 304 conversões, 23 operações de mídia e OCR, com PATH reduzido ao sistema e originais preservados. [Recibo dessa candidata anterior](evidence/0.6.0/citrica-windows-vm-engine-parity.json). O executável final foi verificado separadamente como descrito acima.

## Regressões corrigidas

Uma [captura externa](evidence/0.6.0/windows-symbol-font-native-stack.json) encontrou a interface na enumeração de fontes DirectWrite ao pintar símbolos da roda. Todos esses símbolos, inclusive centro e paginação, passaram a ser vetores próprios. O CI final e os percursos da instalação real passaram sem ampliar os timeouts. A hipótese de fontes frias explica o padrão anterior, mas continua sendo uma inferência.

Outra [captura Python/C++](evidence/0.6.0/windows-old-cli-modal-upgrade.json) encontrou a CLI antiga parada em `QMessageBox::warning` depois de uma corrida no encerramento. O comando agora funciona sem GUI; o instalador extrai seu próprio helper nativo para encerrar inclusive versões antigas. O helper passou por **19 testes no Windows** e [cinco encerramentos da instalação anterior sem sua CLI disponível](evidence/0.6.0/citrica-windows-vm-old-app-stop.json). O comando sem GUI passou por [20 ciclos reais](evidence/0.6.0/citrica-windows-vm-headless-quit.json).

O modelo de rostos passou a ser lido pelo Python e carregado em memória pelo OpenCV, evitando a API de caminho estreito que falhava em diretórios acentuados. As ferramentas de rosto passaram nas 38 operações do pacote final.

Um experimento independente também isolou um problema do diagnóstico periódico do CPython 3.12.10: três controles passaram e três processos com snapshots assíncronos falharam com acesso inválido, sem importar o Cítrica. O snapshot periódico foi removido; a investigação posterior usa um observador externo. [Comparação e reprodutor](evidence/0.6.0/windows-python312-watchdog-comparison.json), [issue primária do CPython](https://github.com/python/cpython/issues/116008#issuecomment-2034190548).

## Ubuntu e GNOME

O DEB foi instalado, aberto como usuário comum e removido em Ubuntu **24.04, 26.04 e 26.10**, incluindo primeira configuração e PNG→PDF→DOCX. O menu usa o executável do pacote mesmo com um portátil antigo antes dele no PATH.

O DEB também passou por **38 operações avançadas no Ubuntu 26.10**, com cinco paletas verificadas e originais preservados. Seu SHA-256 é `1e722fb36376c2a6086e7e4e4dadd463813c9c6a07f23aa4872429058ecb03f6`. As alterações posteriores são específicas do Windows; esse pacote Linux permanece o mesmo artefato validado.

Compositores GNOME/Wayland reais e isolados validaram a roda nos GNOME 46 e 51 do Ubuntu. GNOME 50 foi validado no Fedora com o backend congelado do Ubuntu 24.04, incluindo nove quadros intermediários de animação. Os containers Ubuntu desativaram animações por renderização em software; não se atribui a eles uma medição de fluidez. [Escopo e recibos Ubuntu](validation-0.6.0-ubuntu.json).

## Assinatura e limites

O instalador 0.5.0 com marcador de origem da Internet exibiu o aviso de fornecedor desconhecido na VM. A tela azul específica relatada externamente não foi reproduzida. O instalador final e o aplicativo apresentam `NotSigned`; não há alegação de aviso eliminado.

Em 28 de outubro de 2026, o mantenedor informou que concluiu a verificação Microsoft e apresentou confirmação do envio da candidatura à SignPath. A aprovação da SignPath continua pendente; o painel Microsoft apresentado ainda não contém um produto Cítrica. A identidade do pacote, a adaptação MSIX e a certificação da Store são etapas posteriores. Os instaladores testados acima continuam sem assinatura. [Requisitos e próximos passos](WINDOWS-SIGNING.md). Nenhuma proteção foi desativada e nenhum certificado autoassinado foi instalado para simular confiança pública.

A VM e o CI não representam todos os PCs, GPUs ou documentos. A escala **Qt** de 150% não equivale a testar toda configuração de DPI do monitor Windows. [Resultados estruturados e histórico Windows](validation-0.6.0-windows.json).
