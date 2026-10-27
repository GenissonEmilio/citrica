# Instalar no Ubuntu

Baixe o arquivo **`citrica_<versão>_amd64.deb`** na [release mais recente](https://github.com/GenissonEmilio/citrica/releases/latest). O DEB contém o aplicativo completo: não é necessário instalar Python, Qt ou bibliotecas Python manualmente.

Abra o DEB com o instalador de aplicativos do Ubuntu e confirme a instalação. Se o aplicativo de loja da sua instalação não abrir arquivos DEB locais, use o gerenciador de pacotes do próprio Ubuntu:

```bash
cd ~/Downloads
sudo apt install ./citrica_*_amd64.deb
```

O `apt` também instala as bibliotecas do sistema exigidas pelo aplicativo. Usar somente `dpkg -i` pode deixar dependências pendentes; nesse caso, execute `sudo apt --fix-broken install`.

Abra **Cítrica** no menu de aplicativos. A primeira abertura prepara a integração e o atalho **Super+Shift+C** no seu usuário. Se as configurações indicarem que a extensão ainda não foi carregada, salve seu trabalho, saia da sessão e entre novamente. Fechar e abrir o aplicativo não reinicia o GNOME Shell.

Comece a arrastar um arquivo no aplicativo Arquivos, toque **Shift** e solte o arquivo no formato desejado. **Alt** abre ferramentas, **Ctrl** abre ações e **Esc** cancela. A cópia convertida aparece junto ao original.

## Compatibilidade

| Ubuntu | GNOME padrão | Roda global |
| --- | --- | --- |
| 24.04 LTS | 46 | Integração em validação nativa nesta atualização |
| 26.04 LTS | 50 | Mesma versão principal do GNOME validada no Fedora; instalação DEB em validação |
| 26.10 | 51 | Integração em validação nativa nesta atualização |
| 22.04 LTS | 42 | Sem suporte à roda; o pacote atual também exige glibc mais recente |

A roda requer **GNOME com Wayland**. No Ubuntu 24.04, selecione **Ubuntu** na tela de login, sem a opção **Ubuntu on Xorg**. As variantes Kubuntu, Xubuntu, Lubuntu, Cinnamon e outros desktops não ganham uma roda global somente por instalar o DEB. As configurações mostram a versão detectada e explicam a incompatibilidade.

Os downloads x86_64 oficiais são compilados no Ubuntu 24.04 e exigem **glibc 2.39 ou mais recente**. O pacote registra o piso real do ambiente em que foi construído, para não prometer compatibilidade indevida quando alguém compila em outra distribuição. Não instale manualmente uma glibc de outra versão do Ubuntu.

## Formatos e dependências

Imagens, PDF, PDF→DOCX e DOCX básico incluem seus motores no pacote. FFmpeg habilita áudio/vídeo; LibreOffice amplia as conversões de documentos, planilhas e apresentações. O instalador recomenda esses programas do sistema:

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

`tests/linux/install_smoke.py` instala o DEB em um container Ubuntu descartável, abre o aplicativo como usuário comum, verifica a configuração inicial, converte PNG→PDF→DOCX e remove o pacote. O script recusa execução fora de container e não acessa a sessão gráfica de trabalho. Esse teste de pacote é distinto dos testes de arraste no compositor GNOME/Wayland real.

As versões do Ubuntu e do GNOME são documentadas nas notas oficiais do [Ubuntu 24.04](https://discourse.ubuntu.com/t/ubuntu-24-04-noble-numbat-released/44496), [Ubuntu 26.04](https://documentation.ubuntu.com/release-notes/26.04/) e [Ubuntu 26.10](https://documentation.ubuntu.com/release-notes/26.10/). Os resultados efetivamente concluídos ficam em [VALIDACAO.md](VALIDACAO.md).
