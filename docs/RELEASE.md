O **Cítrica 0.4.0** adiciona disponibilidade para **Windows x64**, com instalador `.exe`, ZIP portátil e a roda de conversão integrada ao desktop. Os pacotes Linux continuam disponíveis.

- **Windows:** aplicativo residente na bandeja, roda transparente de setores arredondados, miniatura central e destaque laranja animado. Arraste um arquivo, pressione **Shift** e solte no formato.
- **Alt** mostra ferramentas e **Ctrl**, ações. O atalho padrão no Windows é **Ctrl+Alt+C**, configurável. Escape cancela; setas/Enter navegam.
- Configurações próprias para Windows, verificação de conflito de atalho, inicialização automática opcional e exportação de diagnóstico.
- Instalador no usuário atual, entrada no menu Iniciar, atalho opcional na área de trabalho e **Enviar para → Cítrica** no Explorer. Aberturas adicionais se comunicam com a instância residente.
- Roda limpa ao reabrir depois de converter, cancelar ou falhar. O arraste solicita cópia para preservar o original, inclusive com Shift pressionado.
- Motor compartilhado: imagens, PDF, arquivos compactados, legendas, mídia e Office conforme as dependências disponíveis. Ferramentas produzem cópias.
- **Linux / GNOME 50 / Wayland:** mantém Shift, Alt, Ctrl e **Super+Shift+C**, com os pacotes RPM, DEB e TAR.GZ.

**Instalação Windows:** execute `citrica-0.4.0-windows-x86_64-setup.exe` ou extraia todo o ZIP portátil e abra `Citrica.exe`. Não é necessário instalar Python. O aplicativo usa permissões normais; encerre pela bandeja quando quiser parar os atalhos. O instalador ainda não tem assinatura digital.

**Dependências Windows:** imagens, PDF, QR e detecção de rostos acompanham o pacote. FFmpeg com ffprobe, LibreOffice e Tesseract x64 com modelo eng são opcionais externos, necessários para mídia, Office e detecção de texto, respectivamente. LocalSend é opcional para compartilhar.

**Validação:** testes automatizados do motor/interface e do executável empacotado; a validação manual no Explorer do Windows do usuário **está pendente do teste externo combinado**. Isso não é declarado concluído por uma compilação bem-sucedida. O [guia para o teste no Windows](https://github.com/GenissonEmilio/citrica/blob/main/docs/WINDOWS.md) inclui instalação, roteiro, diagnóstico e limitações. Resultados em [docs/VALIDACAO.md](https://github.com/GenissonEmilio/citrica/blob/main/docs/VALIDACAO.md).

**Fedora:** instale o RPM e execute `citrica --install-gnome`. Se o GNOME ainda estiver executando uma extensão anterior, saia e entre novamente na sessão para carregar a roda instalada.

**Limites:** roda Linux validada para GNOME 50; outros compositores precisam de integração própria. AirDrop, paridade completa com todos os formatos/algoritmos do Tangerine e imagens animadas/multipágina não são oferecidos. Originais preservados nas conversões; Mover é uma ação explícita. Licença AGPL-3.0-or-later.
