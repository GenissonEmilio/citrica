# Cítrica no Windows

Alvo: Windows x64, com o mesmo fluxo de arrastar → Shift → roda → soltar. O aplicativo permanece na bandeja. A versão Linux 0.6.0 usa a extensão do GNOME 46/50/51 com Wayland.

## Instalar e abrir

A [release 0.6.0](https://github.com/GenissonEmilio/citrica/releases/tag/v0.6.0) inclui todos os motores descritos abaixo. Baixe o [instalador Windows](https://github.com/GenissonEmilio/citrica/releases/download/v0.6.0/citrica-0.6.0-windows-x86_64-setup-unsigned-test.exe) e execute o arquivo terminado em `setup-unsigned-test.exe`. O pacote passou pelo CI completo e pela VM Windows 11 e continua sem assinatura pública; [resultados e escopo dos testes](VALIDACAO-0.6.0.md).

Os arquivos da 0.6.0 mantêm `unsigned-test` no nome para identificar o estado da assinatura. O instalador usa a conta atual, cria a entrada no menu Iniciar e adiciona **Enviar para → Cítrica** no Explorer. Atalho na área de trabalho e inicialização automática são opcionais.

A assinatura Authenticode e a reputação do SmartScreen são verificações diferentes. O relatório `citrica-windows-signing.json` informa se aquele pacote está assinado; um candidato marcado `unsigned` ainda pode exibir **Editor desconhecido**. Não desative o Defender, SmartScreen ou Smart App Control. Consulte [assinatura e distribuição](WINDOWS-SIGNING.md) para os caminhos de certificação/loja e os limites dessa validação.

Alternativa: extraia **todo** o ZIP portátil e abra `Citrica/Citrica.exe`. Mantenha `_internal` ao lado do executável. Não é preciso instalar Python. Abra com permissões normais, no mesmo nível do Explorer; executar o aplicativo como administrador pode impedir o arraste entre as janelas.

O aplicativo no menu abre as configurações. Fechar essa janela mantém o Cítrica na bandeja; o ícone pode estar no menu de ícones ocultos. Clique duas vezes nele para voltar às configurações; use **Sair** para encerrar o aplicativo.

## Usar a roda

1. No Explorer, comece a arrastar uma imagem e continue segurando o botão do mouse.
2. Pressione **Shift**. A roda aparece perto do ponteiro.
3. Continue o movimento até o setor **JPG**, por exemplo, e solte o mouse.
4. Confira a cópia ao lado do arquivo original. O original deve continuar intacto.
5. Abra novamente com **Ctrl+Alt+C**. A roda deve estar vazia.

**Alt** durante o arraste abre ferramentas; **Ctrl** abre ações. **Esc** cancela. Setas e Enter também permitem selecionar/aplicar uma opção. Sem arquivo, clique no centro da roda para escolher arquivos. O atalho global, a tecla de arraste, a animação e a inicialização com o Windows são configuráveis. Conflitos de atalho são informados ao salvar.

A ativação observa tecla e movimento do botão. A seleção da janela de origem do Explorer antecipa a prévia, inclusive com o mouse parado ao tocar Ctrl/Alt/Shift; a operação só é autorizada quando o Windows/Qt entrega a oferta real de arquivo. Drops durante o carregamento aguardam as opções ficarem prontas. Arrastes de texto, URLs da web ou pastas não são aceitos como arquivos para conversão. As conversões solicitam o efeito de cópia ao Explorer, inclusive quando Shift sugere mover.

## Motores e ferramentas

O Cítrica 0.6.0 inclui Python, Qt, Pillow/codecs de imagem, PDF, QR, detecção local de rostos e os motores FFmpeg/FFprobe, LibreOffice e Tesseract com modelo OCR. Não é preciso instalar Word, configurar PATH nem baixar motores ao usar a roda. As versões 0.4.0/0.5.0 exigiam motores externos para parte desses recursos.

- **Áudio/vídeo:** conversões e ferramentas usam o FFmpeg/FFprobe da própria pasta instalada, inclusive **Tamanho alvo**.
- **DOCX e PDF:** PDF→DOCX, DOCX→PDF/TXT e TXT→PDF/DOCX funcionam com os motores incluídos, sem Word/LibreOffice. O modo básico pode alterar layouts avançados; PDFs escaneados continuam como imagens no DOCX, sem OCR automático.
- **Outros documentos Office:** o motor LibreOffice incluído atende DOC/DOCX/ODT/RTF/TXT, XLS/XLSX/ODS/CSV/TSV e PPT/PPTX/ODP. Ele roda sem janela, com perfil temporário separado, sem registrar associações de arquivo ou instalar outro aplicativo no menu.
- **Ocultar texto:** Tesseract e o modelo `eng` acompanham o pacote; a detecção acontece localmente. Revise as áreas detectadas, especialmente em texto pequeno ou baixo contraste.
- **Compartilhar:** LocalSend é opcional; AirDrop não está disponível.

Imagens animadas/multipágina e os formatos não listados no README continuam fora do escopo. As receitas, pins de origem, fontes correspondentes e a distinção entre pacote provisório e pacote de publicação estão em [Motores Windows](WINDOWS-ENGINES.md).

## Roteiro para a validação do amigo

Use cópias de arquivos de teste numa pasta com espaços e acentos no nome. Registre a versão do Windows, resolução/escala e qualquer comportamento diferente do esperado.

- [ ] Instalar, abrir configurações e confirmar o ícone na bandeja.
- [ ] Arrastar um PNG real do Explorer, tocar Shift, escolher JPG e soltar. Conferir dimensões da cópia e original presente.
- [ ] Sem instalar Office, FFmpeg ou Tesseract no sistema, conferir as opções de DOCX/ODT, XLSX/CSV, PPTX, vídeo e áudio. Converter um PDF com texto para DOCX e editar o texto no Word/LibreOffice.
- [ ] Tocar Ctrl com o mouse parado durante o arraste: a roda de ações deve carregar. Repetir com Alt e Shift.
- [ ] Repetir com vários arquivos selecionados e com um arquivo da área de trabalho.
- [ ] Abrir por Ctrl+Alt+C após converter: nenhum arquivo, miniatura ou formato antigo deve permanecer.
- [ ] Cancelar com Esc; tentar uma imagem corrompida; reabrir vazia em ambos os casos.
- [ ] Verificar a aparência, abertura, hover e fechamento, inclusive em outro monitor/escala quando disponível.
- [ ] Alt → Recortar, salvar uma cópia e conferir a área. Ctrl → Copiar caminho; conferir ao colar no Bloco de Notas.
- [ ] Ctrl → Copiar; colar no Explorer em outra pasta. Conferir Terminal, Mover e Prateleira com arquivos de teste.
- [ ] Salvar outro atalho global, acioná-lo fora do Cítrica e depois restaurar Ctrl+Alt+C.
- [ ] Fechar configurações e confirmar que a roda continua funcionando. Encerrar pela bandeja e confirmar que o atalho foi liberado.
- [ ] Validar vídeo/áudio, Office, Tamanho alvo e ocultação de texto na VM limpa. Revisar as regiões detectadas antes de compartilhar.
- [ ] Atualizar/reinstalar, desinstalar e confirmar a remoção de atalhos/inicialização automática.

Em caso de erro, use **Configurações → Salvar diagnóstico para suporte**, informe os passos e envie uma captura/gravação. Logs locais ficam em `%LOCALAPPDATA%/Citrica/Logs/citrica.log`; preferências ficam em `%APPDATA%/Citrica/settings.json`.

CLI e diagnóstico no PowerShell, dentro da pasta instalada/portátil:

```powershell
.\citrica-cli.exe --version
# No Windows PowerShell 5.1, preserve o UTF-8 recebido da CLI antes de usar pipe:
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
.\citrica-cli.exe --doctor | Out-File -Encoding utf8 citrica-diagnostico.json
.\citrica-cli.exe "C:\Teste com acentos\imagem.png" --to jpg
```

## O que foi validado e o que ainda falta

Os testes do motor e da interface Qt são executados no CI Linux e Windows. A matriz do pacote publicado usa o executável congelado com PATH reduzido ao Windows: 50 extensões de entrada, todas as saídas anunciadas e as ferramentas de mídia/OCR. Isso detecta dependências instaladas por acaso na máquina de build. O mesmo instalador publicado passou na VM limpa por instalação, atualização da versão pública 0.5.0, remoção, 38 operações avançadas e 24 arrastes reais no Explorer. A execução efetiva e as evidências estão registradas em [VALIDACAO-0.6.0.md](VALIDACAO-0.6.0.md); isso não equivale a validar todos os PCs, monitores ou documentos do usuário.

Para forçar o motor incluído mesmo com LibreOffice instalado, defina `CITRICA_OFFICE_ENGINE=builtin` antes de iniciar o aplicativo ou a CLI. O padrão automático prefere LibreOffice quando encontrado.
