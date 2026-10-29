# Candidatura SignPath Foundation — acompanhamento

**Recusada em 29 de outubro de 2026**, conforme resposta apresentada pelo mantenedor. A Foundation informou que o projeto ainda não reúne sinais públicos suficientes de adoção, visibilidade e atividade para emitir um certificado em seu nome. A resposta permite nova candidatura quando houver reconhecimento público mais amplo; não apontou defeito técnico no aplicativo. Nenhum certificado foi emitido.

O pedido foi enviado pelo mantenedor em 28 de outubro de 2026. Os dados abaixo preservam a referência preparada para a candidatura; o conteúdo efetivamente enviado não foi conferido. A correspondência privada e os dados de contato não são reproduzidos aqui.

## Dados públicos prontos

| Campo | Informação |
| --- | --- |
| Projeto | Cítrica |
| Mantenedor / dono do repositório | [GenissonEmilio](https://github.com/GenissonEmilio) |
| Repositório | https://github.com/GenissonEmilio/citrica |
| Página / documentação | https://github.com/GenissonEmilio/citrica#readme |
| Licença do projeto | AGPL-3.0-or-later; dependências documentadas em THIRD_PARTY.md e licenses/ |
| Releases Windows existentes | https://github.com/GenissonEmilio/citrica/releases |
| Fonte do instalador | packaging/windows.iss |
| Fonte do empacotamento | packaging/build_windows.py |
| Workflow público de build/testes | .github/workflows/ci.yml |
| Artefatos próprios propostos | Citrica.exe, citrica-cli.exe, instalador Inno Setup e seu desinstalador |
| Componentes upstream | Qt, Python e motores de conversão; não solicitar assinatura Foundation das DLLs/EXEs upstream |

## Texto sugerido para descrição

> Cítrica is an open-source, local file converter for Linux and Windows. On Windows it runs in the system tray and shows a radial menu while users drag files in Explorer. Users choose an output format and receive a separate converted file; conversion does not require uploading files to a conversion service. The public repository includes source code, pinned Python dependencies, Windows packaging scripts and automated tests. We would like to apply for SignPath Foundation signing for our own Windows launchers and Inno Setup installer/uninstaller, linked to GitHub Actions builds. Upstream executable components would be included according to the Foundation's approved artifact configuration, without signing those binaries as our own code.

## Requisitos a confirmar com o serviço

O envio foi feito diretamente pelo mantenedor. A configuração de MFA, os integrantes responsáveis por alterações/revisão/aprovação e os termos precisam seguir as exigências do serviço. Não inferimos dados de contato nem que a configuração de MFA esteja ativa. Os papéis propostos são **GenissonEmilio** como mantenedor, revisor e aprovador, sujeitos à aceitação da Foundation.

Os termos exigem origem verificável dos artefatos, aprovação manual por release, metadados e política pública de assinatura/privacidade. A Foundation avalia também a reputação e elegibilidade do projeto; o serviço pode recusar a solicitação. Consulte os [termos completos](https://signpath.org/terms).

Antes de declarar a política final, revisar o comportamento de rede das integrações e dependências, o inventário de licenças e quais arquivos pertencem ao projeto. Só depois da aprovação adicionar a atribuição oficial exigida e os papéis confirmados à página pública. Não afirmar patrocínio antecipadamente.

## Integração a realizar se aprovado

Guardar as credenciais do serviço nos mecanismos aprovados do CI, limitar quem aprova assinaturas, selecionar os artefatos próprios e ligar a solicitação ao build/tag público. Configurar o callback do Inno para assinar o desinstalador durante a compilação, além do setup. Testar a instalação pelo canal final numa VM com as proteções do Windows ativadas.

O script local `packaging/sign_windows.py` prepara o caminho para um certificado próprio de CA/HSM. Ele não configura nem substitui o serviço SignPath. A candidatura atual foi recusada; qualquer integração futura depende de nova aprovação e das configurações fornecidas pelo serviço. O canal MSIX da Microsoft Store continua independente dessa candidatura.

## Pontos para confirmar com a Foundation

O candidato por fontes testado tem instalador de aproximadamente **473 MiB** e ZIP portátil de **730 MiB**. Não há quota OSS específica confirmada para este projeto; informar esses tamanhos no pedido. A aceitação do desinstalador Inno precisa de confirmação explícita: ele contém código do gerador upstream. O callback de assinatura está preparado para um certificado autorizado, mas não constitui autorização da Foundation. Os componentes de terceiros mantêm suas assinaturas originais ou permanecem sem assinatura; não serão assinados como código próprio.
