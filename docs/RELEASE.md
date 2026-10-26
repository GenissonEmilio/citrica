O **Cítrica 0.5.0** corrige o fluxo da roda no Windows e adiciona **PDF→DOCX em Linux e Windows**, com motores incluídos no aplicativo.

- **Windows / Ctrl, Alt e Shift:** a seleção da janela de origem do Explorer antecipa a prévia enquanto o arraste OLE é negociado. A operação exige a oferta real do arquivo; não utiliza apenas uma seleção presumida.
- Ofertas nativas FileNameW/CF_HDROP são reconhecidas quando o Qt não fornece URLs. Revele a roda sem recriar/elevar novamente a janela durante DragEnter.
- Drops feitos antes de as opções carregarem são mantidos até o motor ficar pronto. Soltar e tocar novamente o mesmo modificador permite nova tentativa.
- **DOCX→PDF/TXT sem instalar Office**, além de TXT→PDF/DOCX. LibreOffice continua opcional para maior fidelidade e necessário para outros formatos Office.
- **PDF→DOCX editável**, com texto, tabelas e imagens conforme o layout. O motor usa um processo separado para permitir cancelamento sem publicar arquivo parcial.
- **Linux / GNOME 50:** a miniatura nativa do arquivo fica acima da roda com Ctrl, Alt e Shift; extensão versão 3, revisão 2.
- Diagnóstico Windows inclui formatos de oferta recebidos, confirmação do arraste e execução elevada. O aplicativo deve usar o mesmo nível normal de permissões do Explorer.

**Windows:** instale `citrica-0.5.0-windows-x86_64-setup.exe` ou extraia o ZIP portátil completo. O atalho padrão é **Ctrl+Alt+C**. **Linux:** RPM, DEB e TAR.GZ; no GNOME, **Super+Shift+C**. Shift converte, Alt abre ferramentas e Ctrl abre ações durante o arraste.

**Validação:** suíte compartilhada, conversões pelo executável empacotado, testes nativos GNOME e Windows, Explorer real em escalas Qt de 100%/150% e instalação/desinstalação. As execuções e os resultados efetivamente concluídos ficam em [VALIDACAO.md](https://github.com/GenissonEmilio/citrica/blob/main/docs/VALIDACAO.md).

**Limites:** layouts Word/PDF avançados podem mudar; PDF escaneado vira DOCX com imagens, sem OCR automático. FFmpeg, Tesseract e LocalSend continuam opcionais externos no Windows. O instalador ainda não tem assinatura digital. A roda Linux requer GNOME 50/Wayland. Originais preservados nas conversões; Mover é uma ação explícita.
