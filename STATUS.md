# Status da implementação

## Pronto

- Aplicativo principal `camera_museu.py`.
- Interface CustomTkinter responsiva e fullscreen.
- Captura da câmera em thread separada.
- Composição pelas áreas transparentes das molduras PNG.
- Galeria, seleção manual, próximo/anterior e opção sem moldura.
- A moldura permanece selecionada até ser trocada manualmente.
- Ajuste ao vivo de posição, zoom, espelhamento e resolução.
- Cronômetro animado, flash e reprodução de `nudge.wav`.
- Salvamento JPEG por data, antes de qualquer tentativa de envio.
- Envio SMTP SSL/STARTTLS em segundo plano.
- Configuração do remetente e teste de autenticação SMTP.
- Senha protegida pelo Gerenciador de Credenciais do Windows.
- Campo da senha bloqueado por autenticação administrativa para visualizar ou editar.
- Logs rotativos sem senha e endereço do visitante mascarado.
- Scripts para instalar dependências e iniciar o aplicativo.

## Validações executadas

- Compilação sintática do arquivo Python.
- Importação de todas as dependências.
- Composição de imagem 1440×900 com uma moldura real.
- Inicialização e encerramento automático da interface.
- Confirmação do backend `WinVaultKeyring` para credenciais.

## Validações que dependem da operação real

- Conferir o enquadramento de cada moldura com a câmera e iluminação finais.
- Testar autenticação e entrega usando a conta SMTP do museu.
- Ajustar assunto/corpo do e-mail e identidade visual, se necessário.
