# Motores offline do Windows

O Cítrica 0.6.0 leva os motores junto do aplicativo. Não baixa programas ao abrir arquivos e não exige um PATH preparado pelo usuário. A árvore `_internal` precisa permanecer ao lado dos dois launchers.

| Local no pacote | Finalidade |
| --- | --- |
| `_internal/tools/ffmpeg/bin` | FFmpeg/FFprobe para áudio, vídeo, metadados, recorte e tamanho alvo |
| `_internal/tools/libreoffice` | Documentos, planilhas e apresentações, com perfil temporário isolado |
| `_internal/ocr` | DLL Tesseract, dependências necessárias e `tessdata/eng.traineddata` |
| `_internal/engines.json` | Versões, origens e hashes dos artefatos de build |
| `_internal/engine-files.sha256.json` | Inventário dos arquivos dos motores |
| `_internal/engine-sources.zip` | Fontes originais de FFmpeg/codecs/OCR e receita efetivamente utilizada no build por fontes |

O localizador prefere essa árvore. A variável `CITRICA_WINDOWS_ENGINES` permite testar o código-fonte com os mesmos motores preparados. Ela não substitui o motor de um aplicativo que já possui seus próprios arquivos. `CITRICA_OFFICE_ENGINE=builtin` força o renderizador DOCX básico para diagnóstico.

## Dois caminhos de preparação

O preparador `packaging/prepare_windows_engines.py` serve ao **candidato funcional provisório**: extrai FFmpeg Gyan, LibreOffice MSI e Tesseract UB Mannheim, todos fixados por URL e SHA-256 em `windows-engines.lock.json`. A origem do FFmpeg é um fornecedor indicado pela [página oficial](https://ffmpeg.org/download.html); a do Tesseract aparece na [página UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). A extração não executa o instalador Tesseract. O MSI é usado com `/a /qn`, sem instalar ou registrar o LibreOffice.

Esse caminho está marcado `provisional-vendor-binaries` em `engines.json`. Preservar a licença principal de um binário GPL não basta para estabelecer suas fontes correspondentes: o Gyan liga várias bibliotecas estaticamente, e o instalador UB traz DLLs de outros projetos. O pacote provisório não deve ser promovido a distribuição pública com uma alegação de conformidade completa.

O caminho de publicação é `packaging/build_windows_source_engines.py`. Ele compila FFmpeg e as bibliotecas que o aplicativo usa, além de Tesseract/Leptonica; preserva os arquivos-fonte originais, pins, receitas e configuração. O próprio instalador/ZIP leva `engine-sources.zip`, que também é exportado como asset separado. O motor Office permanece o LibreOffice original, com seus avisos completos e o endereço das fontes oficiais.

O build por fontes desliga dependências opcionais que a aplicação não usa. FFmpeg inclui x264, libvpx, Opus, Vorbis/Ogg, LAME, dav1d e zlib; mantém os codecs/filtros internos. Tesseract recebe pixels RGB já decodificados pela Pillow, por isso Leptonica pode dispensar seus leitores de arquivo e Tesseract pode dispensar CURL/Archive/TIFF. OCR é compilado com o runtime MSVC estático (`/MT`). Isso reduz dependências ocultas; a matriz e a VM precisam confirmar os binários efetivos.

## Compilar por fontes

Use Windows x64, Python 3.12+, CMake, Visual Studio 2022 com compilador C++, Inno Setup e MSYS2 MINGW64. O workflow `windows-engines-source.yml` prepara os compiladores; as versões do toolchain são registradas no ZIP de fontes. Os artefatos-fonte do motor têm hashes em `packaging/windows-sources.lock.json`.

No MSYS2, os pacotes de compilação são `base-devel`, `perl`, `mingw-w64-x86_64-gcc`, `mingw-w64-x86_64-nasm`, `mingw-w64-x86_64-pkgconf`, `mingw-w64-x86_64-meson` e `mingw-w64-x86_64-ninja`. Depois, no PowerShell do repositório:

```powershell
python packaging/build_windows_source_engines.py --msys-bash C:/msys64/usr/bin/bash.exe
$env:CITRICA_WINDOWS_ENGINES = "$PWD/build/windows-source-engines"
$env:CITRICA_RELEASE_REQUIRE_ENGINE_SOURCES = "1"
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
python packaging/build_windows.py
```

Os downloads acontecem nessa preparação explícita do build. Um arquivo de origem alterado é recusado por SHA-256; não há fallback que ignore o hash. Para uma publicação, `CITRICA_RELEASE_REQUIRE_ENGINE_SOURCES=1` recusa o candidato provisório e a ausência do ZIP de fontes. As instruções são reproduzíveis; igualdade bit a bit entre toolchains diferentes ainda não foi estabelecida e não é anunciada.

Para recompilar a partir de `engine-sources.zip`, extraia-o e siga o `README-SOURCES.txt` incluído. A pasta `downloads` contém os arquivos originais e o modelo que o script verifica/reutiliza como cache. `--office-from` permite reutilizar a pasta Office da instalação recebida e dispensa o download do MSI durante essa recompilação.

## Verificação

`tests/windows/engine_parity.py citrica-cli.exe` remove os diretórios de ferramentas do PATH e as variáveis de override. Exige que FFmpeg e Office venham da pasta instalada, exercita 50 extensões em 304 conversões, testa ferramentas de áudio/vídeo e carrega efetivamente a DLL/modelo OCR. Os fixtures e as saídas usam pastas com espaços e acentos; hashes conferem a preservação dos originais.

A mesma matriz pode ser comparada no Linux com `--system-engines`. O relatório separa resultados de conversão, ferramentas e OCR; ele não representa documentos arbitrários nem certificação de segurança. Assinatura, SmartScreen e loja são tratados em [WINDOWS-SIGNING.md](WINDOWS-SIGNING.md).
