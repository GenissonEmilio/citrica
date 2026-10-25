O **Cítrica 0.3.0** corrige a seleção que permanecia depois de converter e refaz a aparência da roda a partir do vídeo oficial do Tangerine.

- A roda reabre **vazia** pelo atalho: sem arquivo anterior, miniatura, formato destacado ou cache do arraste. Fechamento, Escape, erro e respostas atrasadas também limpam a seleção.
- Novo **anel de setores creme/pêssego**, com cantos arredondados, centro transparente, miniatura proporcional e cápsula de tamanho/ação. O setor sob o ponteiro fica laranja.
- Abertura de 240 ms, expansão elástica dos setores, hover animado, troca com desvanecimento e fechamento de 130 ms. As capacidades são antecipadas durante o arraste.
- **Shift** para formatos, **Alt** para ferramentas, **Ctrl** para ações; **Super+Shift+C** abre a roda. Configurações indicam quando o GNOME ainda executa uma revisão anterior.
- Mantém as conversões locais e as ferramentas de imagem, PDF, áudio/vídeo. Originais preservados; publicação sem sobrescrita.

**Fedora / GNOME 50 / Wayland:** instale o RPM e execute `citrica --install-gnome`. O portátil inclui `install.sh`. Após atualizar, **saia e entre novamente na sessão do GNOME** para carregar o código novo da extensão. Fechar a janela de configurações não recarrega o Shell.

**Validação:** 88 testes do motor/interface; percursos nativos em GNOME 50/Wayland isolado no Fedora, incluindo regressões de reabertura, Nautilus, atalhos, ferramentas e gravação real da animação. A validação do executável empacotado e as evidências estão em [docs/VALIDACAO.md](https://github.com/GenissonEmilio/citrica/blob/main/docs/VALIDACAO.md). Veja a [captura nativa](https://github.com/GenissonEmilio/citrica/raw/refs/heads/main/docs/wheel-native.mp4).

RPM, DEB e portátil x86_64; glibc >= 2.39. FFmpeg e LibreOffice são dependências opcionais do sistema. Prévia específica para GNOME 50, sem roda global KDE/GNOME antigo. Compartilhamento exige LocalSend; AirDrop e paridade completa com todos os formatos/algoritmos comerciais não são oferecidos. Licença AGPL-3.0-or-later.
