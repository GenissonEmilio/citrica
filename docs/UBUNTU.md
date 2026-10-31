# Instalar o Cítrica 0.7.0 no Ubuntu

A [versão 0.7.0](https://github.com/GenissonEmilio/citrica/releases/tag/v0.7.0) oferece instalador DEB, editores visuais e cinco estilos de roda no GNOME 46/50/51 com Wayland. A [validação da atualização](VALIDACAO-0.7.0.md) distingue os resultados novos do histórico da 0.6.0 descrito abaixo.

1. Baixe diretamente [citrica_0.7.0_amd64.deb](https://github.com/GenissonEmilio/citrica/releases/download/v0.7.0/citrica_0.7.0_amd64.deb), sem precisar entrar no GitHub.
2. Localize o DEB na pasta de downloads. Ele contém o aplicativo, Python, Qt e os motores de imagem/PDF; essas bibliotecas não precisam ser instaladas manualmente.
3. Abra o DEB com o instalador de aplicativos do Ubuntu e confirme a instalação.

Se a loja da sua instalação não abrir arquivos DEB locais, abra um terminal na pasta que contém o arquivo baixado e use o gerenciador de pacotes do Ubuntu:

```bash
sudo apt update
sudo apt install ./citrica_0.7.0_amd64.deb
```

O `apt` resolve e instala automaticamente as bibliotecas do sistema exigidas pelo aplicativo. A conexão com a internet é usada para obter essas dependências. Usar somente `dpkg -i` pode deixar dependências pendentes; nesse caso, execute `sudo apt --fix-broken install`.

Abra **Cítrica** no menu de aplicativos. A primeira abertura prepara a integração e o atalho **Super+Shift+C** no seu usuário. Se as configurações indicarem que a extensão ainda não foi carregada, salve seu trabalho, saia da sessão e entre novamente. Fechar e abrir o aplicativo não reinicia o GNOME Shell.

Comece a arrastar um arquivo no aplicativo Arquivos, toque **Shift** e solte o arquivo no formato desejado. **Alt** abre ferramentas, **Ctrl** abre ações e **Esc** cancela. A cópia convertida aparece junto ao original.

## Compatibilidade

| Ubuntu | GNOME padrão | Roda global |
| --- | --- | --- |
| 24.04 LTS | 46 | DEB aprovado; roda, conversão, atalhos e Arquivos validados em compositor isolado |
| 26.04 LTS | 50 | DEB aprovado; GNOME 50 validado separadamente no Fedora |
| 26.10 | 51 | DEB aprovado; roda, conversão, atalhos e miniatura validados em compositor isolado |
| 22.04 LTS | 42 | Sem suporte à roda; o pacote atual também exige glibc mais recente |

A roda requer **GNOME com Wayland**. No Ubuntu 24.04, selecione **Ubuntu** na tela de login, sem a opção **Ubuntu on Xorg**. As variantes Kubuntu, Xubuntu, Lubuntu, Cinnamon e outros desktops não ganham uma roda global somente por instalar o DEB. As configurações mostram a versão detectada e explicam a incompatibilidade.

Os downloads x86_64 oficiais são compilados no Ubuntu 24.04 e exigem **glibc 2.39 ou mais recente**. O pacote registra o piso real do ambiente em que foi construído, para não prometer compatibilidade indevida quando alguém compila em outra distribuição. Não instale manualmente uma glibc de outra versão do Ubuntu.

## Formatos e dependências

Imagens, PDF, PDF→DOCX e DOCX básico incluem seus motores no pacote. FFmpeg habilita áudio/vídeo; LibreOffice amplia as conversões de documentos, planilhas e apresentações. O DEB recomenda esses programas do sistema, e o `apt` normalmente os instala junto com o aplicativo. Se as opções correspondentes não aparecerem, confira:

```bash
sudo apt install ffmpeg libreoffice
```

PDF escaneado continua sendo uma imagem dentro do DOCX; não há OCR automático nessa conversão. O arquivo original é preservado.

Para consultar a instalação e dependências:

```bash
citrica --doctor
```

Para remover o aplicativo pelo terminal:

```bash
sudo apt remove citrica
```

## Validação reproduzível

Na 0.7.0, o DEB final do commit `027e785` passou instalação, abertura, conversão e remoção em Ubuntu 24.04, 26.04 e 26.10 no [CI 41155927692](https://github.com/GenissonEmilio/citrica/actions/runs/41155927692). Os [recibos atuais](VALIDACAO-0.7.0.md) também registram a matriz Linux de 304 conversões e o teste dos cinco estilos, editores e animações no GNOME 50/Fedora. Os percursos de desktop GNOME 46/51 descritos a seguir pertencem à 0.6.0.

`tests/linux/install_smoke.py` instala o DEB em um container Ubuntu descartável, abre o aplicativo como usuário comum, verifica a configuração inicial, converte PNG→PDF→DOCX e remove o pacote. O script recusa execução fora de container e não acessa a sessão gráfica de trabalho. Esse teste de pacote é distinto dos testes de arraste no compositor GNOME/Wayland real.

No [CI 40735116402](https://github.com/GenissonEmilio/citrica/actions/runs/40735116402), o mesmo DEB publicado na 0.6.0 passou nos três containers limpos: **Ubuntu 24.04, 26.04 e 26.10**. A abertura ocorreu como usuário comum, inclusive com um portátil antigo simulado antes do aplicativo no PATH. Os relatórios `citrica-ubuntu-VERSAO-validation.json` estão nos artifacts de evidências de cada job. Esses jobs validam os pacotes Linux; os resultados Windows estão registrados separadamente em [Validação 0.6.0](VALIDACAO-0.6.0.md).

O mesmo DEB do CI ff90885 passou também por 38 operações avançadas no Ubuntu 26.10 como usuário comum: cinco paletas exatas, ferramentas de imagem/PDF, rostos, OCR, QR e recusas esperadas de entradas inválidas. As nove entradas sintéticas permaneceram intactas. [Relatório do pacote instalado](evidence/0.6.0/citrica-ubuntu-2610-final-static-tools.json).

Nos testes Ubuntu com renderização por software, o próprio GNOME desativou animações do desktop. Nesses ambientes foi verificado o fluxo funcional. No teste separado do GNOME 50/Fedora, o executável congelado da candidata registrou nove quadros intermediários reais na abertura. A validação nativa Ubuntu 24.04 incluiu o gerenciador Arquivos real, com arraste, conversão e copiar/colar. No Ubuntu 26.10, a comparação de pixels confirmou a miniatura acima da roda nos três modos.

A etapa adicional `--setup` com compositor ativo também passou no GNOME 50/Fedora: o pacote congelado registrou versão 0.6.0, Wayland suportado e o comando correto do backend. A janela de configurações dessa etapa foi renderizada em modo offscreen. A etapa adicional não foi repetida nos GNOME 46/51; a primeira abertura offscreen passou nos três Ubuntu.

As versões do Ubuntu e do GNOME são documentadas nas notas oficiais do [Ubuntu 24.04](https://discourse.ubuntu.com/t/ubuntu-24-04-noble-numbat-released/44496), [Ubuntu 26.04](https://documentation.ubuntu.com/release-notes/26.04/) e [Ubuntu 26.10](https://documentation.ubuntu.com/release-notes/26.10/). O [relatório Ubuntu da candidata 0.6.0](validation-0.6.0-ubuntu.json) registra o escopo e as evidências; [VALIDACAO.md](VALIDACAO.md) mantém o histórico da versão pública 0.5.0.
