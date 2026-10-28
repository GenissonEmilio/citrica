# Microsoft Store: pacote MSIX do Cítrica

Este é um caminho de empacotamento separado do instalador Inno e do ZIP da
release 0.6.0. Os binários de uma release publicada não devem ser substituídos
para adicionar suporte à Store. O pacote Store exige uma compilação que já
contenha o adaptador `citrica-package.exe` e o runtime com suporte à identidade,
StartupTask, preferências e IPC de MSIX.

**Estado:** o builder e seus testes locais não comprovam compilação pelo
Windows SDK, instalação na VM, aprovação no WACK, assinatura ou certificação da
Store. Esses resultados são registrados separadamente pelos testes reais.

## Identidade pública

`packaging/windows-store-identity.json` contém somente valores públicos obtidos
do Partner Center:

| Campo | Valor |
| --- | --- |
| Package/Identity/Name | `Emilians.Ctrica` |
| Package/Identity/Publisher | `CN=4F26C959-AACA-4166-BA27-5DE331C059E7` |
| PublisherDisplayName | `Emilians` |
| Nome visível | `Cítrica` |
| Store ID | `9NV389WMRJNC` |
| Package Family Name | `Emilians.Ctrica_dtz50gxq3qxna` |
| Versão do pacote Store | `1.6.0.0` |

A versão do produto pode continuar sendo `0.6.0`. A versão do pacote é
independente: a orientação da Store exige primeiro componente acima de zero e
quarto componente zero. `MaxVersionTested` é uma declaração do manifest, não um
registro de que a VM ou o WACK já passaram.

Não colocar senhas, certificados privados, tokens, arquivos de conta ou capturas
do Partner Center nesse JSON, no payload ou nos artefatos públicos.

## Compilar sem alterar o payload

No Windows, com o SDK oficial instalado e um **novo** payload PyInstaller
completo, já contendo o helper de pacote:

```powershell
python packaging/build_msix.py `
  --payload dist/Citrica `
  --identity packaging/windows-store-identity.json `
  --staging build/msix-stage `
  --output release/msix `
  --mode both
```

`--mode` aceita `store`, `qa` ou `both` (padrão). É possível indicar o caminho
do SDK com `--makeappx C:\caminho\do\SDK\makeappx.exe`. Sem essa opção, o
builder procura a versão mais recente do SDK x64 instalado e depois o PATH.
Não baixa ferramentas ou motores e não executa arquivos do payload.

Staging e saída devem ser caminhos novos, independentes, fora do payload. O
builder não mescla, limpa ou sobrescreve diretórios existentes. Se uma execução
falhar, escolha caminhos novos ou remova manualmente apenas os diretórios de
build conhecidos antes de tentar novamente.

O builder valida a presença dos executáveis x64, Python, Qt, plugin Windows,
helper, motores, fontes correspondentes e inventário SHA-256 dos motores. Copia
o payload inteiro e verifica hashes antes e depois, rejeitando links, colisões
de nomes Windows e contêineres de chaves privadas conhecidos. Essa verificação
não substitui os testes de execução nem uma revisão do conteúdo fornecido.

O XML é gerado com ElementTree. Os logos PNG 44×44, 150×150 e 50×50 são
rasterizados pelo Qt a partir do próprio `citrica/assets/citrica.svg`. O comando
de compilação é `MakeAppx.exe pack /d <staging> /p <novo arquivo.msix>`; a
validação do SDK não é desativada com `/nv`.

Em Linux, `--stage-only` permite inspecionar manifest, cópia e logos. Não produz
MSIX e registra `staged-only-not-msix-validated`; testes com um MakeAppx simulado
também não constituem compilação ou instalação real.

## Duas variantes que não podem ser confundidas

| Saída | Finalidade |
| --- | --- |
| `Citrica_1.6.0.0_x64_store-unsigned.msix` | Identidade real; entrada sem assinatura para submissão ao Partner Center. |
| `Citrica_1.6.0.0_x64_qa-unsigned-NOT-FOR-STORE.msix` | Teste unsigned na VM; nunca enviar à Store ou distribuir como versão verificada. |

A variante QA tem nome `Emilians.Ctrica.UnsignedQA`, nome visível
`Cítrica · QA unsigned` e acrescenta ao Publisher o marcador oficial
`OID.2.25.311729368913984317654407730594956997722=1`. Portanto possui **outra
identidade/PFN**. Os relatórios QA não atribuem a ela o Store ID ou PFN real.
Cada variante tem seu próprio manifest, staging, pacote, log e relatório JSON.

O relatório distingue staging, validação MakeAppx, assinatura, teste na VM e
certificação. Um MakeAppx bem-sucedido não marca os demais como aprovados.

## Runtime e integrações

O manifest usa `uap10:RuntimeBehavior="packagedClassicApp"`,
`uap10:TrustLevel="mediumIL"` e a capability restrita `runFullTrust`, com Windows
Desktop mínimo `10.0.19041.0`. Esse é um aplicativo desktop no usuário normal;
o pacote não solicita execução como administrador nem AppContainer.

Os namespaces adicionais são `uap/windows10`, `desktop/windows10`,
`uap/windows10/10` e `foundation/windows10/restrictedcapabilities`, todos sob
`http://schemas.microsoft.com/appx/manifest/`. O StartupTask é declarado numa
`desktop:Extension` com categoria `windows.startupTask`, executável
`Citrica\Citrica.exe`, `uap10:Parameters="--background"`, TaskId **CitricaStartup**
e `Enabled="false"`. Os atributos de ativação/trust são herdados da Application.

O adaptador de runtime deve consultar e alterar o StartupTask pela API Windows,
respeitando `DisabledByUser` e `DisabledByPolicy`; o checkbox não pode continuar
dependendo de HKCU\Run em MSIX. Preferências devem usar LocalFolder, cache e
logs LocalCache, e temporários TemporaryFolder. WindowsApps é somente leitura.
O perfil temporário do LibreOffice e as saídas junto ao arquivo original também
precisam ser exercitados no pacote instalado.

A roda Win32/Qt, bandeja, clipboard, motores filhos e comunicação com o Explorer
precisam manter o mesmo nível de integridade do Explorer. Testar o namespace de
pipe MSIX, distinto do Inno, em GUI, CLI e prévia do Explorer. MSIX não executa
ações do `windows.iss`; em particular, a entrada Enviar para do instalador Inno
não é criada automaticamente por este manifest.

## Validação real na VM

1. Verificar versão do Windows, identidade e disponibilidade de `AllowUnsigned`
   antes de qualquer instalação. Não alterar Defender, SmartScreen, registro de
   políticas ou Developer Mode como parte do builder.
2. Na VM Windows 11, instalar apenas a variante QA com o fluxo oficial elevado
   `Add-AppxPackage -Path <qa.msix> -AllowUnsigned`. O guia unsigned não exige
   Developer Mode, mas exige o OID e elevação para conteúdo executável. Esse
   teste não prova a identidade ou assinatura reais da Store.
3. Ativar pelo AUMID do pacote, conferir identidade dentro do GUI/CLI e testar
   atalhos, Shift/Ctrl/Alt, Explorer real, miniatura, cancelamento, clipboard,
   conversões e ferramentas offline com todos os motores, sem runtimes extras.
4. Habilitar startup pela UI, sair/entrar e confirmar só a bandeja. Desabilitar
   pelas configurações do Windows e confirmar que o app respeita essa escolha.
5. Atualizar um pacote de versão inferior para a candidata, verificando
   persistência de preferências e caminhos novos de instalação; remover com
   residente aberto e conferir ausência de processos/atalhos órfãos e
   preservação dos arquivos originais e convertidos.
6. Executar WACK na sessão interativa da VM: `appcert.exe reset`, seguido de
   `appcert.exe test -packagefullname <nome completo> -reportoutputpath <xml>`.
   Guardar XML/HTML e resolver falhas materiais; não tratar testes unitários
   como substitutos desse relatório.

Para testar a identidade **real** fora da Store, a orientação para MSIX completo
exige assinatura de desenvolvimento e confiança explícita no certificado da
VM em `LocalMachine\TrustedPeople`, não numa raiz pública falsa. Esse passo não
é feito pelo builder e exige autorização específica depois de existir um pacote
revisável. Confiança apenas em CurrentUser não é garantida pelo App Installer.

Para distribuição pela Store, a Microsoft assina o MSIX após a certificação;
não é necessário comprar um certificado público para esse fluxo. Isso **não**
assina o EXE Inno ou o ZIP do GitHub. A submissão deve justificar `runFullTrust`
pelo menu global Win32, OLE/clipboard, bandeja e motores locais, e concluir os
demais requisitos do Partner Center. Este builder não faz submissões.

## Fontes oficiais

- [Identity e versão do pacote](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering).
- [Application e ativação mediumIL](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-application).
- [StartupTask e controle do usuário](https://learn.microsoft.com/en-us/uwp/api/windows.applicationmodel.startuptask).
- [desktop:Extension e uap10:Parameters](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-desktop-extension).
- [Virtualização e diretórios de aplicativos desktop](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).
- [MakeAppx do Windows SDK](https://learn.microsoft.com/en-us/windows/msix/package/create-app-package-with-makeappx-tool).
- [Unsigned, OID e permissões](https://learn.microsoft.com/en-us/windows/msix/package/unsigned-package).
- [Certificados confiados para testes](https://learn.microsoft.com/en-us/windows/msix/app-installer/troubleshoot-appinstaller-issues#trusted-certificates).
- [Windows App Certification Kit](https://learn.microsoft.com/en-us/windows/uwp/debug-test-perf/windows-app-certification-kit).
- [Assinatura no fluxo Microsoft Store](https://learn.microsoft.com/en-us/windows/apps/publish/get-started).
- [Capability runFullTrust e revisão da Store](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/app-capability-declarations).
