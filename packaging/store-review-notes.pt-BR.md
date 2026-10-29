# Roteiro para revisão do Cítrica na Microsoft Store

Texto de apoio para o campo de informações adicionais de teste. O roteiro não
constitui um relatório de aprovação: os resultados do pacote instalado são
registrados separadamente em `docs/evidence/store/`.

O Cítrica é um conversor local de arquivos para Windows Desktop x64. A interface
está em português do Brasil. Não há conta, login, senha de teste, compra ou
serviço remoto necessário para as conversões. Os motores de conversão acompanham
o pacote.

1. Abra o Cítrica pelo menu Iniciar. A tela de configurações apresenta o atalho,
   a opção de animação, a inicialização na bandeja e o estado dos motores.
2. Pressione `Ctrl+Alt+C` para mostrar a roda junto ao ponteiro. `Esc` cancela.
   O atalho pode ser personalizado nas configurações.
3. No Explorador de Arquivos, arraste um PNG mantendo o botão do mouse
   pressionado. Durante o arraste, pressione `Shift`, mova o ponteiro sobre
   `PDF` na roda e solte. A cópia convertida deve aparecer junto ao original.
4. Arraste um PDF do mesmo modo e selecione `DOCX`. PDFs com texto permitem
   edição do texto no resultado; PDFs escaneados permanecem como imagens nessa
   conversão. Documentos complexos podem apresentar diferenças de layout.
5. Durante outro arraste, `Alt` mostra as ferramentas disponíveis para o tipo de
   arquivo e `Ctrl` mostra ações. A miniatura do arquivo deve ficar acima da
   roda. Pressione `Esc` para cancelar.
6. Fechar a tela de configurações mantém o aplicativo na bandeja. A opção
   **Sair** da bandeja encerra o residente. A inicialização com o Windows é
   opcional e deve respeitar a escolha do usuário nas configurações do sistema.

O aplicativo opera com o nível normal do usuário. `runFullTrust` é utilizado
pela integração desktop da roda, atalhos globais, arrastes OLE, área de
transferência, bandeja e subprocessos locais de conversão. A execução cotidiana
não pede elevação.

Os originais são preservados nas conversões. A ação **Mover** é uma operação
separada, solicitada pelo usuário. O compartilhamento opcional abre o aplicativo
LocalSend, que precisa estar instalado separadamente e não é necessário para
avaliar o conversor.
