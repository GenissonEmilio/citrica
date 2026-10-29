# Privacidade no Cítrica

Atualizada em 28 de outubro de 2026.

O Cítrica é um conversor de arquivos local e de código aberto, mantido por [GenissonEmilio](https://github.com/GenissonEmilio/citrica). O nome do editor na Microsoft Store é **Emilians**. Esta página descreve o comportamento do aplicativo; serviços de distribuição e aplicativos externos têm suas próprias políticas.

## Arquivos e processamento local

O aplicativo acessa os arquivos e pastas que você seleciona, arrasta para a roda ou fornece pela linha de comando. Esses arquivos podem conter dados pessoais. Conversões, leitura de metadados, leitura de QR, reconhecimento de texto e detecção de regiões de rostos são processados no computador. O Cítrica não oferece um servidor próprio de conversão nem envia automaticamente os arquivos a um serviço de conversão.

A detecção de rostos serve para localizar regiões da imagem; o aplicativo não identifica pessoas nem mantém um cadastro de identidades faciais. As ferramentas de ocultação exigem que você revise o resultado.

As conversões normalmente criam uma cópia, preservando o original. Ações como mover arquivos só acontecem quando você as solicita. Você escolhe os arquivos que serão copiados para a área de transferência ou passados a outro programa.

## Preferências, temporários e diagnóstico

Preferências, arquivos temporários e registros de funcionamento ficam no computador. Preferências incluem atalho, tecla de arraste e animação. A integração da roda observa os atalhos e o estado do arraste para operar a interface; não existe um recurso de envio de histórico de digitação.

Os registros de erro podem conter mensagens, nomes de arquivos, caminhos e informações técnicas do ambiente. No Windows, os logs são locais e rotativos. A opção **Salvar diagnóstico para suporte** gera um arquivo local com versão, sistema, dependências, estado da interface e preferências; ela não envia esse arquivo automaticamente.

Você pode apagar os arquivos convertidos, diagnósticos e dados locais que não deseja manter. Arquivos temporários são usados durante as operações; falhas ou encerramento inesperado podem deixar arquivos para limpeza posterior. Backups e sincronização de pastas configurados por você no sistema operacional seguem as configurações e políticas desses serviços.

## Rede e programas externos

O Cítrica não implementa publicidade, conta de usuário, telemetria de uso ou venda de dados. Os motores Windows acompanham o pacote; sua utilização não exige baixar motores ao abrir um arquivo. No Linux, o gerenciador de pacotes pode obter dependências durante a instalação.

A ação opcional **Compartilhar** abre o LocalSend, quando instalado, com os arquivos escolhidos. O compartilhamento passa a ser operado por esse aplicativo. Abrir um arquivo convertido em outro programa também fica sujeito ao comportamento desse programa, inclusive a acesso a conteúdo externo que o próprio documento possa referenciar.

GitHub e Microsoft Store recebem os dados relacionados a downloads, contas, instalação ou serviços da plataforma conforme suas próprias políticas. Isso não equivale ao envio de arquivos pelo conversor.

## Suporte e alterações

O canal de suporte é a [página de issues do projeto](https://github.com/GenissonEmilio/citrica/issues). Os relatos publicados ali são públicos. Revise o conteúdo antes de compartilhar arquivos, capturas ou diagnósticos; não é necessário publicar documentos pessoais para relatar um problema.

Mudanças no comportamento descrito serão refletidas nesta página e nas notas de versão.
