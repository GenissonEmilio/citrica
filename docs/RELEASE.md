O **Cítrica 0.7.0** traz personalização da roda e novos espaços de edição para Linux e Windows.

- **Cinco estilos:** Cítrica, Aquarela, Vidro claro, Grafite e Alto contraste. A aba **Personalizar a roda** mostra a prévia e salva sua escolha; os estilos translúcidos deixam o desktop aparecer.
- **Imagem:** canvas amplo, seleção com alças, área móvel, proporções de recorte, controles numéricos, sliders e prévia dos ajustes, anotações e fundos.
- **Vídeo e áudio:** player interno com reproduzir/pausar/navegar; linha do tempo com miniaturas ou forma de onda; alças de seleção e campos de tempo sincronizados para recortar. Em áudio, a ferramenta Censurar áudio substitui o trecho selecionado por um tom.
- **PDF e outras ferramentas:** prévia de páginas, seleção e reordenação visual, painel de parâmetros, cancelamento, **Salvar cópia** e **Abrir resultado**.
- **Linux:** Compartilhar reconhece LocalSend via Flatpak de sistema/usuário, binário nativo e AppImage executável em locais usuais ou registrado no menu. Arquivos são encaminhados ao LocalSend para concluir o envio.
- **Windows:** soltar fora de uma opção fecha e limpa a roda, inclusive com dados atrasados do Explorer ou um novo arraste depois de **Mais**. Drops válidos continuam aguardando a análise do arquivo antes de executar.

**Instalação:** Linux recebe DEB, RPM e TAR.GZ. No Ubuntu, use o instalador do sistema ou `sudo apt install ./citrica_0.7.0_amd64.deb`. A roda Linux exige GNOME 46/50/51 com Wayland. Após atualizar a extensão, saia e entre novamente na sessão para carregar o código novo.

**Windows:** a [Microsoft Store](https://apps.microsoft.com/detail/9nv389wmrjnc?hl=pt-BR&gl=BR) é o canal com distribuição assinada pela Microsoft. A versão do pacote desta atualização é **1.7.0.0**, correspondente ao produto **0.7.0**; o envio e a certificação são separados da release do GitHub. O EXE e o ZIP alternativos preservam `unsigned-test` no nome e **não têm assinatura pública**. A SignPath Foundation recusou a candidatura inicial; a aprovação da conta Microsoft não assina esses arquivos.

**Validação e limites:** [relatório 0.7.0](https://github.com/GenissonEmilio/citrica/blob/v0.7.0/docs/VALIDACAO-0.7.0.md). Os editores são focados nas ferramentas do Cítrica; não oferecem montagem multitrilha ou todas as funções de um editor de vídeo completo. O player usa QtMultimedia e depende dos codecs do backend. Miniaturas, quadros e forma de onda usam FFmpeg/ffprobe; codecs sem reprodução interna podem continuar com essas prévias quando o FFmpeg consegue decodificá-los. PDF→DOCX mantém texto editável quando disponível, com possíveis diferenças de layout; PDFs escaneados continuam como imagens. As conversões preservam originais; **Mover** é uma ação explícita.
