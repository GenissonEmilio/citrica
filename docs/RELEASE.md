O **Cítrica 0.6.0** inclui os motores de conversão no Windows e amplia a instalação nativa no Ubuntu. Arquivos que dependem de áudio/vídeo ou Office deixam de exigir programas instalados à parte no Windows.

- **Windows offline:** FFmpeg/FFprobe, LibreOffice e Tesseract com modelo OCR acompanham instalador e portátil. Codecs e OCR têm build por fontes fixadas e pacote de fontes correspondentes.
- **Pastas com acentos:** os modelos de texto e rostos são lidos por APIs que preservam caminhos Unicode. Atualizações substituem o runtime privado completo, removendo DLLs antigas.
- **Ubuntu:** DEB construído no Ubuntu 24.04, dependências do sistema corretas, configuração inicial por usuário e roda GNOME 46/50/51 em Wayland. O menu abre a instalação nativa mesmo com um portátil antigo no PATH.
- **Roda:** Shift converte, Alt abre ferramentas e Ctrl abre ações durante o arraste. A miniatura permanece acima da roda e a reabertura limpa a seleção. Atalhos padrão: Super+Shift+C no GNOME e Ctrl+Alt+C no Windows.

**Instalação:** Linux recebe DEB, RPM e TAR.GZ. No Ubuntu, abra o DEB pelo instalador do sistema ou use `sudo apt install ./citrica_0.6.0_amd64.deb`. No Windows, use o instalador completo ou extraia todo o ZIP portátil, preservando `_internal` junto dos launchers.

**Validação:** os recibos distinguem a matriz de conversões, testes do Explorer real, VM Windows 11, instalação/atualização/remoção e testes Ubuntu/GNOME. Consulte [Validação 0.6.0](VALIDACAO-0.6.0.md) e os relatórios que acompanham cada pacote; sucesso no CI não representa todos os PCs ou documentos.

**Assinatura:** consulte `citrica-windows-signing.json` para o estado do arquivo baixado. Candidatos identificados como `unsigned-test` são testes sem editor verificado. A publicação assinada depende de uma identidade aprovada; uma assinatura não garante reputação SmartScreen imediata. [Opções de distribuição](WINDOWS-SIGNING.md).

PDF→DOCX mantém texto editável quando disponível; PDFs escaneados viram páginas com imagens, sem OCR automático nessa conversão. Layouts complexos podem mudar. A roda Linux requer GNOME/Wayland; outros desktops não recebem uma roda global por instalar o DEB. Compartilhamento continua dependendo de LocalSend. As conversões preservam os originais; Mover é uma ação explícita.
