Primeira prévia funcional do **Cítrica**, um conversor local de arquivos para Linux inspirado no fluxo de arrastar e converter do Tangerine, com implementação e identidade próprias.

- Interface Qt em português, menu radial e área flutuante para arrastar e soltar.
- Imagens, PDF, áudio, vídeo, documentos Office, legendas e arquivos compactados, conforme os motores disponíveis.
- Conversão em lote, qualidade/largura, limpeza de metadados e união de PDFs.
- Cópias ao lado do original, publicação atômica e proteção contra sobrescrita.
- CLI e instalador de menus de contexto para Nautilus, Nemo e Dolphin.
- Pacotes **RPM, DEB e TAR.GZ** para **Linux x86_64**, compilados em Ubuntu 24.04, com **glibc >= 2.39**. Python/Qt/imagem/PDF incluídos; FFmpeg e LibreOffice opcionais, instalados separadamente.
- `SHA256SUMS` e imagem de prévia incluídos.

**Wayland:** use a área flutuante ou menus de contexto. Esta versão não intercepta Shift globalmente durante o arraste em outro aplicativo. Janelas acima das demais e bandeja dependem do compositor.

**Limitações:** prévia 0.1.0, sem paridade completa com o Tangerine. Sem OCR, recorte de mídia, SVG ou RAR; imagens animadas e multipágina são recusadas. Confira a tabela de formatos e as limitações no README. Compressão não garante tamanho menor; exportação Office depende do LibreOffice.

O CI verifica o motor, conversões reais, a interface e a abertura do binário empacotado antes da publicação. Validação manual entre gerenciadores de arquivos e diferentes compositores ainda está pendente. Licença AGPL-3.0-or-later.
