# CI de compatibilidade Linux e Windows

Esta configuração prepara candidatos para validação. Um workflow verde não significa que a aplicação recebeu reputação SmartScreen, aprovação da Store ou aceitação SignPath.

## Build de teste por workflow_dispatch

No workflow **Testes e release Linux e Windows**, escolha a branch candidata e execute manualmente. O dispatch não cria tag nem release. Por padrão, o Windows usa motores offline provisórios preparados por `packaging/prepare_windows_engines.py`, com versões/origens/SHA-256 registrados em `packaging/windows-engines.lock.json`. Esse caminho de binários vendor serve somente para QA na VM; não satisfaz a exigência de fontes correspondentes de uma release.

Para testar o caminho de publicação, marque **windows_engine_sources** no dispatch. O CI prepara MSYS2/MinGW e confere Visual Studio 2022/CMake, então executa `packaging/build_windows_source_engines.py` para compilar FFmpeg/codecs e OCR dos fontes fixados em `packaging/windows-sources.lock.json`. O resultado inclui `engine-sources.zip`, receitas, configuração e registros de toolchain. O LibreOffice continua vindo do MSI upstream documentado. Esta opção compila no próprio run, sem reaproveitar artefatos de procedência diferente. A compilação demora mais; a assinatura continua desabilitada nesse candidato de teste.

O caminho vendor precisa de 7-Zip, já listado na imagem Windows Server 2022 do GitHub. O CI verifica sua presença; não instala FFmpeg, Tesseract ou LibreOffice no sistema. Ambos os caminhos produzem a árvore `build/windows-engines`, exposta aos testes por `CITRICA_WINDOWS_ENGINES` e copiada para `_internal` no pacote. [Inventário oficial do runner](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md).

Os testes unitários sintetizam mídia usando o FFmpeg dessa árvore. O build congelado executa a matriz de todas as extensões suportadas, removendo esse PATH e os overrides para comprovar o uso dos motores distribuídos. As regressões da roda também preservam o teste do motor básico DOCX/PDF, forçado com `CITRICA_OFFICE_ENGINE=builtin` dentro do roteiro Explorer.

Os downloads do dispatch têm estes identificadores:

- Artifact `citrica-windows-x86_64-unsigned-test`.
- Instalador e portátil terminados em `-unsigned-test.exe` e `-unsigned-test.zip`.
- `UNSIGNED-TEST-BUILD.txt` e `citrica-windows-signing.json` com `status: unsigned`.

Esses arquivos são destinados à VM e não constituem uma publicação com editor verificado. O renomeio acontece depois dos testes de instalação/Explorer, e o arquivo de checksums é recalculado ao final.

## Matriz Linux e DEB

O build Ubuntu 24.04 roda a mesma matriz de conversões com os motores do sistema e publica `citrica-linux-engine-parity.json`. O artifact `citrica-native-packages` contém o `.deb` gerado.

Três jobs independentes baixam esse mesmo pacote em containers limpos **Ubuntu 24.04, 26.04 e 26.10**. O roteiro `tests/linux/install_smoke.py` instala via apt, abre a interface e faz a primeira configuração como usuário comum, converte PNG→PDF→DOCX e remove o pacote. Os relatórios `citrica-ubuntu-VERSAO-validation.json` registram o resultado. Isso não substitui os testes nativos da roda no GNOME, que são uma validação separada.

## Tags e publicação

Os pacotes Windows de tags públicas exigem assinatura Authenticode. Sem `CITRICA_SIGN_CERT_SHA1` válido e o certificado/chave privada acessível no Certificate Store do runner, o job Windows falha antes de preparar os motores e compilar seu pacote. A variável contém somente o identificador público do certificado; ela não provisiona a chave. O build Linux é independente dessa exigência de assinatura Windows.

Tags sempre escolhem a compilação dos motores por fonte; a preparação vendor é ignorada, independentemente dos inputs. `CITRICA_RELEASE_REQUIRE_ENGINE_SOURCES=1` exige a procedência `compiled-from-pinned-sources` e o pacote de fontes no build. Os mesmos testes de paridade, instalação e Explorer são executados sobre o resultado. O CI inclui as fontes correspondentes entre os arquivos finais e confere seu SHA-256 no relatório antes de criar a release.

O caminho atual é uma preparação para certificado próprio acessível pelo Windows/HSM. Nenhuma chave privada é importada pelo workflow. Se for adotado SignPath ou Store, o mantenedor precisará configurar o fluxo do serviço aprovado; preencher um thumbprint não substitui essa etapa. Consulte [WINDOWS-SIGNING.md](WINDOWS-SIGNING.md).

O job de publicação só prossegue após Linux, Windows e todos os containers Ubuntu. Ele rejeita recibos sem assinatura válida/timestamp e qualquer arquivo `unsigned-test`, e então cria uma release em rascunho para a revisão final. O relatório informa separadamente que reputação SmartScreen não foi verificada. Sem credencial real, essa etapa fica deliberadamente indisponível; o dispatch de testes continua utilizável.

## Evidências

Os artifacts incluem relatórios de conversão, Explorer, instalação e assinatura. Falhas Windows preservam os logs da extração dos motores e dos testes. Quantidades de testes passam a ser as efetivamente exibidas pelo CI: o LibreOffice bundled permite executar o teste Office que antes era pulado por ausência do programa.

Os workflows foram conferidos localmente com **actionlint 1.7.12**. As execuções do CI/VM, e seus resultados, devem ser registrados após ocorrerem; a preparação do workflow não é apresentada como uma execução já aprovada.
