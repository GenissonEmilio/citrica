# Candidatura SignPath Foundation — rascunho revisável

**Não enviada. Não constitui aprovação, certificado ou política já aceita.** Preparada em 27 de outubro de 2026 para o mantenedor revisar em [SignPath: Apply](https://signpath.org/apply).

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

## Confirmações do mantenedor antes de enviar

O responsável precisa preencher seu contato diretamente no formulário e confirmar MFA, os integrantes responsáveis por alterações/revisão/aprovação e sua aceitação dos termos. Não inferimos dados de contato nem que a configuração de MFA esteja ativa. Os papéis propostos são **GenissonEmilio** como mantenedor, revisor e aprovador, sujeitos à aceitação da Foundation.

Os termos exigem origem verificável dos artefatos, aprovação manual por release, metadados e política pública de assinatura/privacidade. A Foundation avalia também a reputação e elegibilidade do projeto; o serviço pode recusar a solicitação. Consulte os [termos completos](https://signpath.org/terms).

Antes de declarar a política final, revisar o comportamento de rede das integrações e dependências, o inventário de licenças e quais arquivos pertencem ao projeto. Só depois da aprovação adicionar a atribuição oficial exigida e os papéis confirmados à página pública. Não afirmar patrocínio antecipadamente.

## Integração a realizar se aprovado

Guardar as credenciais do serviço nos mecanismos aprovados do CI, limitar quem aprova assinaturas, selecionar os artefatos próprios e ligar a solicitação ao build/tag público. Configurar o callback do Inno para assinar o desinstalador durante a compilação, além do setup. Testar a instalação pelo canal final numa VM com as proteções do Windows ativadas.

O script local `packaging/sign_windows.py` prepara o caminho para um certificado próprio de CA/HSM. Ele não configura nem substitui o serviço SignPath. A submissão deste rascunho ao serviço continua dependendo de uma ação explícita do mantenedor.
