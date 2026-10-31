# Roteiro para revisão do Cítrica na Microsoft Store

Atualização produto 0.7.0 / MSIX 1.7.0.0. Texto de apoio para o campo de informações adicionais de teste. O roteiro não
constitui um relatório de aprovação: os resultados do pacote instalado são
registrados separadamente em `docs/evidence/0.7.0/` (histórico em `docs/evidence/store/`).

O Cítrica é um conversor local de arquivos para Windows Desktop x64. A interface
está em português do Brasil. Não há conta, login, senha de teste, compra ou
serviço remoto necessário para as conversões. Os motores de conversão acompanham
o pacote.

Código-fonte do runtime desta atualização:
https://github.com/GenissonEmilio/citrica/tree/027e7855cb9f80242acb573d8fe22e8a1f25f049
As fontes correspondentes dos motores e seus avisos acompanham o aplicativo.

1. Abra o Cítrica pelo menu Iniciar. Geral e atalhos apresenta o atalho, a
   animação, a inicialização na bandeja e o estado dos motores. Na aba Personalizar
   a roda, escolha um dos cinco estilos e use Salvar e testar roda.
2. Pressione `Ctrl+Alt+C` para mostrar a roda junto ao ponteiro. `Esc` cancela.
   O atalho pode ser personalizado nas configurações.
3. No Explorador de Arquivos, arraste um PNG mantendo o botão do mouse
   pressionado. Durante o arraste, pressione `Shift`, mova o ponteiro sobre
   `PDF` na roda e solte. A cópia convertida deve aparecer junto ao original.
4. Arraste um PDF do mesmo modo e selecione `DOCX`. PDFs com texto permitem
   edição do texto no resultado; PDFs escaneados permanecem como imagens nessa
   conversão. Documentos complexos podem apresentar diferenças de layout.
5. Durante outro arraste, `Alt` mostra as ferramentas disponíveis para o tipo de
   arquivo e `Ctrl` mostra ações. A roda apresenta a prévia ou o ícone do arquivo
   quando disponível. Pressione `Esc` para cancelar.
6. Solte outro arraste fora da roda: ela deve fechar e reabrir vazia. Em Alt,
   Recortar abre o novo canvas; em vídeo/áudio, Cortar tempo abre o player com
   linha do tempo e alças. Salvar cópia preserva o original. PDF permite navegar
   e reorganizar páginas na ferramenta correspondente.
7. Fechar a tela de configurações mantém o aplicativo na bandeja. A opção
   **Sair** da bandeja encerra o residente. A inicialização com o Windows é
   opcional e deve respeitar a escolha do usuário nas configurações do sistema.

Os editores são focados nas operações selecionadas; não há montagem multitrilha,
transições ou edição completa de documentos Office. O player de vídeo/áudio usa
QtMultimedia. A leitura da duração e as prévias de miniaturas, quadros e forma de
onda usam FFmpeg/ffprobe. A reprodução depende dos codecs do backend; quando um
codec não abre no player, a alternativa por quadros pode continuar disponível
se o FFmpeg conseguir decodificá-lo. A ferramenta Censurar áudio aplica um tom
ao trecho selecionado de um arquivo de áudio.

O aplicativo opera com o nível normal do usuário. `runFullTrust` é utilizado
pela integração desktop da roda, atalhos globais, arrastes OLE, área de
transferência, bandeja e subprocessos locais de conversão. A execução cotidiana
não pede elevação.

Os originais são preservados nas conversões. A ação **Mover** é uma operação
separada, solicitada pelo usuário. O compartilhamento opcional abre o aplicativo
LocalSend, que precisa estar instalado separadamente e não é necessário para
avaliar o conversor.
