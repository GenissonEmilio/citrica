# Assinatura e distribuição confiável no Windows

Pesquisa e preparação: **28 de outubro de 2026**. Estado atualizado em **29 de outubro de 2026**. Este documento não atesta que uma release esteja assinada: essa informação depende da verificação dos arquivos finais. Metadados, checksum SHA-256 e um instalador funcional não substituem Authenticode.

## O aviso azul

O Microsoft Defender SmartScreen considera a reputação do arquivo e do editor. Uma assinatura confiável identifica o editor e permite acumular reputação entre versões. Uma aplicação nova ainda pode receber o aviso; certificados EV também não garantem liberação imediata. Certificado autoassinado não oferece confiança pública. No Windows 11, Smart App Control pode acrescentar outras verificações. Não é necessário desativar essas proteções para desenvolver a solução. [Microsoft: reputação SmartScreen](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

Na VM limpa, baixe o instalador pelo Edge para preservar a origem da Internet, registre a tela e confira a assinatura antes de instalar. Uma cópia por pasta compartilhada pode não reproduzir a mesma decisão do SmartScreen. Se houver alerta de malware, registre também a detecção exata; isso exige uma investigação diferente do aviso de editor desconhecido.

## Opções para o mantenedor

| Canal | O que depende do mantenedor | Situação da Cítrica |
| --- | --- | --- |
| SignPath Foundation | Solicitação e aprovação do projeto; configuração do serviço e aprovação humana de cada assinatura. | [Candidatura recusada](SIGNPATH-APPLICATION.md) em 29/10/2026 por insuficiência de sinais públicos de adoção e visibilidade; nenhum certificado emitido. |
| Microsoft Store com MSIX | Conta verificada, identidade de pacote, adaptação e testes do MSIX, certificação da loja. | [Cítrica publicado na Microsoft Store](https://apps.microsoft.com/detail/9nv389wmrjnc?hl=pt-BR&gl=BR) em 29/10/2026. Store ID `9NV389WMRJNC`, pacote submetido `1.6.0.0`. [Testes e recibo de publicação](WINDOWS-STORE.md). |
| Download EXE com certificado próprio | Certificado de assinatura de código emitido por CA, validação de identidade e acesso ao token/HSM ou serviço do emissor. | Ferramenta de assinatura preparada; certificado não provisionado. |
| Azure Artifact Signing Public Trust | Elegibilidade geográfica e validação Microsoft. | Atualmente indisponível para pessoa física residente no Brasil. |

A Microsoft assina gratuitamente os pacotes **MSIX distribuídos pela Store**. Publicar EXE/MSI na Store exige assinatura Authenticode própria em todos os arquivos PE incluídos, além do instalador. O pacote atual contém componentes upstream sem assinatura; assinar somente nossos launchers/setup não atende esse canal. [Política 10.2.9](https://learn.microsoft.com/windows/apps/publish/store-policies). O cadastro individual no novo fluxo é gratuito e requer conta Microsoft, documento e selfie, enviados diretamente à Microsoft; comece em [storedeveloper.microsoft.com](https://storedeveloper.microsoft.com/) → **Get started for free → Individual developer**. O fluxo global atende quase 200 mercados; a confirmação da conta brasileira ocorre no portal, não deve ser simulada usando outro país. [Tipos de assinatura](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options), [cadastro individual](https://learn.microsoft.com/en-us/windows/apps/publish/whats-new-individual-developer).

O Artifact Signing possui infraestrutura na região Brazil South, mas isso **não** torna residentes brasileiros elegíveis para identidade Public Trust: indivíduos precisam residir nos EUA ou Canadá. As regras podem mudar; confira os pré-requisitos antes de contratar. [Microsoft: pré-requisitos](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart).

Certificados comerciais têm custo definido pelo emissor e exigências de identidade/armazenamento da chave. Não foi feita compra, cadastro, envio de documentos ou aceitação de contrato em nome do mantenedor. A opção gratuita da SignPath depende da avaliação e reputação do projeto, não é um direito automático. Se aprovada, a assinatura identifica **SignPath Foundation** como titular do certificado. A elegibilidade do desinstalador gerado pelo Inno deve ser confirmada expressamente com o serviço; a capacidade técnica do callback não equivale à aprovação desse arquivo. [Opções Microsoft](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options), [SignPath Foundation](https://signpath.org/).

## Ferramenta incluída para certificado próprio

`packaging/sign_windows.py` usa o **SignTool do Windows SDK** e um certificado já disponível no Windows Certificate Store `My`, inclusive quando a chave privada é fornecida por um token/HSM compatível. O programa não importa PFX, não recebe senha e não cria certificado. SHA-1 abaixo é apenas o identificador do certificado; assinatura e timestamp usam **SHA-256**. [SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).

Exemplo no PowerShell de uma máquina de assinatura autorizada:

```powershell
# Substitua pelo thumbprint real do certificado de assinatura emitido pela CA.
$env:CITRICA_SIGN_CERT_SHA1 = 'THUMBPRINT_REAL_DE_40_DIGITOS_HEXADECIMAIS'
$env:CITRICA_SIGNING_REQUIRED = '1'
# Se necessário, informe o caminho real do Windows SDK:
$env:CITRICA_SIGNTOOL = 'C:\Program Files (x86)\Windows Kits\10\bin\VERSAO_DO_SDK\x64\signtool.exe'

python packaging/sign_windows.py --sign --report build\assinatura-launchers.json `
  dist\Citrica\Citrica.exe dist\Citrica\citrica-cli.exe dist\Citrica\citrica-stop.exe dist\Citrica\citrica-package.exe

python packaging/sign_windows.py --verify --report build\assinatura-setup.json `
  release\citrica-VERSAO-windows-x86_64-setup.exe
```

O valor de exemplo é deliberadamente inválido; é necessário fornecer um certificado real. `CITRICA_SIGN_MACHINE_STORE=1` seleciona `LocalMachine\My`; o padrão é `CurrentUser\My`. `CITRICA_SIGN_TIMESTAMP_URL` permite escolher o serviço RFC 3161 do emissor. Um erro de assinatura, confiança, certificado diferente do selecionado, timestamp ausente ou aviso do SignTool interrompe a operação. O relatório registra o hash final e os certificados apresentados; não certifica a reputação SmartScreen.

Assinaturas válidas de fornecedores são preservadas. Uma assinatura já existente e inválida interrompe o processo. `--payload PASTA` seleciona todos os EXE/DLL/PYD recursivamente; use somente se seu contrato de assinatura permitir assinar os componentes selecionados. **Não use essa seleção com o programa Foundation para assinar DLLs de outros projetos.** A verificação integral pode reprovar uma biblioteca upstream sem assinatura mesmo se os launchers e o instalador forem assinados.

## Ordem de empacotamento

1. Compilar e testar os executáveis, com os metadados de produto/versão.
2. Assinar os launchers próprios e os helpers nativos `citrica-stop.exe` e `citrica-package.exe`, antes de criar o ZIP ou compilar o instalador.
3. Configurar Inno Setup com `inno_signing_arguments(config)`. O `windows.iss` habilita `SignTool=citrica` e `SignedUninstaller=yes` somente com `SigningEnabled`.
4. Compilar: o callback assina e verifica Setup e o desinstalador embutido.
5. Verificar o instalador final; instalar/desinstalar numa VM limpa; gerar checksums apenas após as assinaturas. Não modificar os binários depois.

Inno precisa executar a assinatura durante a compilação para incluir um desinstalador assinado: assinar somente o EXE final não cobre esse arquivo. [Inno: SignTool](https://jrsoftware.org/ishelp/topic_setup_signtool.htm), [SignedUninstaller](https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm).

`CITRICA_SIGNING_REQUIRED=1` permite que um canal destinado a releases assinadas falhe quando falta configuração, em vez de publicar silenciosamente sem assinatura. Sem certificado, o build de desenvolvimento continua possível e deve ser identificado como **não assinado**. Nenhum segredo ou variável de assinatura estava configurado neste repositório durante a preparação; chaves privadas devem permanecer no token/HSM/serviço escolhido.

## Integração com SignPath e Store

O helper local não se conecta à SignPath. Depois da aprovação, configure o fluxo oficial do serviço, restringindo assinatura aos artefatos próprios e vinculando-os ao build público do GitHub. A candidatura preparada lista os pontos ainda não confirmados; não publique uma declaração de patrocínio ou de certificado Foundation antes da aprovação.

MSIX é outro canal, que precisa usar a identidade real fornecida pelo Partner Center. Depois de verificar a conta e reservar o produto, os campos públicos necessários são **Package/Identity/Name**, **Package/Identity/Publisher** e **Package/Properties/PublisherDisplayName**, em Product management → Product identity. Não precisamos receber documento, selfie ou senha. [Identidade do aplicativo](https://learn.microsoft.com/en-us/windows/apps/publish/view-app-identity-details). Antes da submissão, validar o aplicativo desktop empacotado, roda global, tray, subprocessos, startup e preferências; não basta colocar uma assinatura em um manifesto fictício. Os resultados funcionais, o WACK local e a publicação do Cítrica estão registrados em [Microsoft Store](WINDOWS-STORE.md). A certificação oficial ocorre no Partner Center. [Requisitos de pacotes Microsoft](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering).

O produto Cítrica foi reservado em 28/10/2026 e os três campos oficiais de identidade foram obtidos. O MSIX `1.6.0.0` passou no MakeAppx oficial, foi enviado para certificação e publicado em 29/10/2026. Para repetir o cadastro em outro projeto, o fluxo no painel é **Novo produto → Aplicativo MSIX ou PWA**, verificar a disponibilidade do nome escolhido pelo mantenedor e reservá-lo. Depois, abrir **Gerenciamento de produtos → Identidade do produto** e fornecer os três campos acima para preparar o pacote MSIX. Criar o produto não publica o aplicativo; envio do pacote e certificação são etapas posteriores. [Fluxo oficial de cadastro e submissão](https://learn.microsoft.com/en-us/windows/apps/publish/get-started).

O canal MSIX publicado e sua variante de QA são descritos em [Microsoft Store](WINDOWS-STORE.md). A assinatura fornecida pela loja pertence a esse canal; os binários Windows da release GitHub 0.6.0 permanecem os mesmos, sem assinatura pública.
