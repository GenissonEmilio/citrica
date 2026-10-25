O **Cítrica 0.2.0** corrige o fluxo da prévia anterior: arraste um arquivo no desktop, toque **Shift** e solte no formato da **roda nativa animada**, sem abrir a janela grande de conversão.

- Integração **GNOME Shell 50 / Wayland**: Shift para converter, Alt para ferramentas, Ctrl para ações; Esc para cancelar, setas/Enter para navegar.
- Atalho padrão **Super+Shift+C**, configuração de atalho/modificador/animação e verificação de conflitos.
- Diálogos específicos para recorte visual, ajustes, anotações, fundos, ocultação, metadados e ferramentas de PDF/áudio/vídeo.
- Tamanho alvo para imagem, PDF, áudio e vídeo; detecção local de rostos/texto e leitura de QR. Modelos locais incluídos nos pacotes.
- Originais preservados nas conversões/ferramentas; publicação atômica, sem sobrescrita.
- RPM, DEB, portátil x86_64 e SHA256SUMS. glibc >= 2.39; Python/Qt/imagem/PDF incluídos. FFmpeg e LibreOffice são dependências opcionais do sistema.

**Fedora / GNOME 50:** instale o RPM e execute `citrica --install-gnome`. Saia e entre na sessão para o Shell carregar a extensão. O aplicativo do menu abre as configurações. O portátil tem `install.sh` para instalação no usuário.

**Validação:** suíte de conversões e interface, teste do executável empacotado e teste real em compositor GNOME 50/Wayland isolado no Fedora. Detalhes reproduzíveis, imagens e limites em [docs/VALIDACAO.md](https://github.com/GenissonEmilio/citrica/blob/main/docs/VALIDACAO.md).

**Limites:** prévia para GNOME 50; não há roda global KDE/GNOME antigo. Não é paridade completa com os 275 formatos do Tangerine. Compartilhar exige LocalSend e envio confirmado nele; AirDrop não está implementado. Detecção automática pode omitir regiões e requer revisão. SVG/RAR/Pages/EPUB, PDF→Office e imagens animadas/multipágina continuam fora do escopo. Licença AGPL-3.0-or-later.
