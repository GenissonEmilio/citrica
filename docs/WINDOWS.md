# Cítrica 0.5.0 no Windows

Alvo: Windows x64, com o mesmo fluxo de arrastar → Shift → roda → soltar. O aplicativo permanece na bandeja. A versão Linux continua usando a extensão do GNOME 50.

## Instalar e abrir

Baixe `citrica-0.5.0-windows-x86_64-setup.exe` da release. O instalador usa a conta atual, cria a entrada no menu Iniciar e adiciona **Enviar para → Cítrica** no Explorer. Atalho na área de trabalho e inicialização automática são opcionais.

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

O pacote inclui Python, Qt, Pillow/codecs de imagem, PDF, QR e detecção local de rostos. As ferramentas disponíveis são filtradas pelo tipo de arquivo e pelas dependências encontradas.

- **Áudio/vídeo:** instale FFmpeg com **ffmpeg.exe e ffprobe.exe no PATH** e reinicie o Cítrica. Downloads de builds Windows são indicados em https://ffmpeg.org/download.html.
- **DOCX e PDF:** PDF→DOCX, DOCX→PDF/TXT e TXT→PDF/DOCX funcionam com os motores incluídos, sem Word/LibreOffice. O modo básico pode alterar layouts avançados; PDFs escaneados continuam como imagens no DOCX, sem OCR automático.
- **Outros documentos Office:** instale LibreOffice em seu local padrão para DOC/ODT/RTF, planilhas, apresentações e maior fidelidade de DOCX→PDF. O Cítrica reconhece `LibreOffice/program/soffice.com` em Program Files.
- **Ocultar texto:** instale Tesseract x64 com o modelo `eng` no local padrão `Program Files/Tesseract-OCR`. A DLL e `tessdata/eng.traineddata` precisam estar presentes. Links Windows são indicados em https://tesseract-ocr.github.io/tessdoc/Installation.html.
- **Compartilhar:** LocalSend é opcional; AirDrop não está disponível.

FFmpeg, LibreOffice e Tesseract são programas opcionais externos nesta distribuição Windows. Imagens animadas/multipágina e os formatos não listados no README continuam fora do escopo. O instalador ainda não tem assinatura digital.

## Roteiro para a validação do amigo

Use cópias de arquivos de teste numa pasta com espaços e acentos no nome. Registre a versão do Windows, resolução/escala e qualquer comportamento diferente do esperado.

- [ ] Instalar, abrir configurações e confirmar o ícone na bandeja.
- [ ] Arrastar um PNG real do Explorer, tocar Shift, escolher JPG e soltar. Conferir dimensões da cópia e original presente.
- [ ] Sem instalar LibreOffice, arrastar DOCX com Shift e conferir PDF/TXT; converter um PDF com texto para DOCX e editar o texto no Word/LibreOffice.
- [ ] Tocar Ctrl com o mouse parado durante o arraste: a roda de ações deve carregar. Repetir com Alt e Shift.
- [ ] Repetir com vários arquivos selecionados e com um arquivo da área de trabalho.
- [ ] Abrir por Ctrl+Alt+C após converter: nenhum arquivo, miniatura ou formato antigo deve permanecer.
- [ ] Cancelar com Esc; tentar uma imagem corrompida; reabrir vazia em ambos os casos.
- [ ] Verificar a aparência, abertura, hover e fechamento, inclusive em outro monitor/escala quando disponível.
- [ ] Alt → Recortar, salvar uma cópia e conferir a área. Ctrl → Copiar caminho; conferir ao colar no Bloco de Notas.
- [ ] Ctrl → Copiar; colar no Explorer em outra pasta. Conferir Terminal, Mover e Prateleira com arquivos de teste.
- [ ] Salvar outro atalho global, acioná-lo fora do Cítrica e depois restaurar Ctrl+Alt+C.
- [ ] Fechar configurações e confirmar que a roda continua funcionando. Encerrar pela bandeja e confirmar que o atalho foi liberado.
- [ ] Se instalar os motores opcionais: validar vídeo/áudio, Office e ocultação de texto. Revisar as regiões detectadas antes de compartilhar.
- [ ] Atualizar/reinstalar, desinstalar e confirmar a remoção de atalhos/inicialização automática.

Em caso de erro, use **Configurações → Salvar diagnóstico para suporte**, informe os passos e envie uma captura/gravação. Logs locais ficam em `%LOCALAPPDATA%/Citrica/Logs/citrica.log`; preferências ficam em `%APPDATA%/Citrica/settings.json`.

CLI e diagnóstico no PowerShell, dentro da pasta instalada/portátil:

```powershell
.\citrica-cli.exe --version
.\citrica-cli.exe --doctor | Out-File -Encoding utf8 citrica-diagnostico.json
.\citrica-cli.exe "C:\Teste com acentos\imagem.png" --to jpg
```

## O que foi validado e o que ainda falta

Os testes do motor e da interface Qt são executados no CI Linux e Windows. O pacote Windows passa por testes usando o executável congelado. Resultados de integração específicos do Windows são publicados quando disponíveis. Os testes adicionais da 0.5.0 usam o Explorer real em duas escalas Qt e arquivos controlados, sem LibreOffice. A execução efetiva e as evidências estão registradas em VALIDACAO.md; isso não equivale a validar todos os PCs, monitores ou documentos do usuário.

Para forçar o motor incluído mesmo com LibreOffice instalado, defina `CITRICA_OFFICE_ENGINE=builtin` antes de iniciar o aplicativo ou a CLI. O padrão automático prefere LibreOffice quando encontrado.
