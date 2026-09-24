# Planejamento do Camera Museu DEN

## 1. Objetivo

Criar um aplicativo de cabine fotográfica para Windows, executado por `camera_museu.py`, que:

- mostre a câmera ao vivo com fundo/moldura selecionável;
- faça uma contagem regressiva animada antes da captura;
- reproduza `nudge.wav` no instante da foto;
- salve a composição final em `fotos/`;
- envie a foto ao endereço digitado na tela;
- permita configurar o e-mail e a senha do remetente;
- preserve uma interface fluida, leve e apropriada para quiosque.

## 2. Base visual observada no executável

O `Camera_Definitive.exe` foi aberto e inspecionado. O novo projeto manterá as melhores características reconhecíveis:

- palco fotográfico ocupando toda a janela;
- fundo temático cobrindo a tela;
- câmera recortada/posicionada sobre a arte;
- barra superior compacta com “Tirar Foto”, “Moldura”, campo de e-mail e engrenagem;
- janela de configurações com setas para mover a câmera, botão de centralizar e controles `+`/`-` para zoom.

Melhorias planejadas:

- hierarquia visual mais limpa em CustomTkinter;
- controles maiores e estados visuais claros;
- cronômetro 3–2–1 animado sem congelar o vídeo;
- galeria de fundos em vez de depender apenas de seletor de arquivo;
- configuração completa do remetente e botão de teste;
- envio em segundo plano, com confirmação e opção de tentar novamente;
- senha fora de arquivos de texto;
- mensagens de erro compreensíveis para câmera, arquivo e rede.

## 3. Escopo funcional

### 3.1 Inicialização (`__init__`)

- Criar a janela principal e aplicar tema CustomTkinter.
- Carregar preferências locais.
- Abrir a câmera configurada com OpenCV.
- Indexar imagens de uma pasta local configurável e `assets/fundos/`.
- Carregar o fundo ativo e o som de captura.
- Montar a barra de ações, o palco de vídeo e as mensagens de status.
- Iniciar `atualizar_video()` usando `after()`, nunca um loop bloqueante.
- Detectar ausência da câmera e oferecer nova tentativa.

### 3.2 Vídeo (`atualizar_video`)

- Ler o frame mais recente.
- Espelhar horizontalmente, se habilitado.
- Aplicar escala e deslocamento configurados.
- Recortar a câmera pela área transparente da moldura ou por máscara configurável.
- Compor câmera e fundo preservando a proporção da janela.
- Converter BGR → RGB → PIL/ImageTk e atualizar somente o widget existente.
- Limitar a atualização a aproximadamente 24–30 FPS para reduzir CPU.

### 3.3 Captura (`iniciar_captura` / `tirar_foto`)

1. Validar câmera, destino de e-mail e estado atual.
2. Bloquear cliques repetidos no botão.
3. Exibir contagem 3–2–1 com escala e opacidade simulada.
4. Manter o vídeo ao vivo durante a contagem.
5. Capturar o frame em resolução cheia.
6. Aplicar exatamente o mesmo enquadramento/fundo mostrado na prévia.
7. Reproduzir `assets/audio/nudge.wav` sem bloquear a interface.
8. Executar um flash branco curto.
9. Salvar como `fotos/YYYY-MM-DD/AAAA-MM-DD_HH-MM-SS.jpg`.
10. Mostrar a prévia final e iniciar o envio em uma thread de trabalho.
11. Exibir sucesso, falha e “Tentar novamente”.

### 3.4 Fundos e molduras

- Abrir uma galeria com miniaturas encontradas nas duas pastas configuradas.
- Aceitar PNG, JPG, JPEG e WEBP.
- Usar PNG com transparência como moldura sobreposta.
- Tratar imagem opaca como fundo; a câmera será desenhada na área configurada.
- Permitir “Escolher outro arquivo”.
- Permitir próximo/anterior na tela principal para comutar rapidamente.
- Guardar apenas o caminho do último item escolhido.
- Se o arquivo sumir, voltar ao primeiro fundo válido sem encerrar o app.

### 3.5 E-mail do visitante

- Campo principal para o destinatário.
- Normalização de espaços e validação sintática antes da captura.
- Limpar o endereço automaticamente depois do envio bem-sucedido, com atraso curto.
- Não registrar o endereço completo nos logs; mascarar parte do texto.

### 3.6 Configurações do remetente

Campos:

- e-mail remetente;
- senha de aplicativo/senha SMTP, com exibir/ocultar;
- nome de exibição;
- servidor SMTP;
- porta;
- segurança: SSL ou STARTTLS;
- câmera/dispositivo;
- resolução preferida;
- duração do cronômetro;
- pasta de fundos;
- pasta de fotos;
- espelhamento e fullscreen.

Ações:

- Salvar;
- Testar conexão/envio;
- Cancelar;
- Restaurar padrões;
- setas de posição, zoom `+`/`-` e centralizar, como no aplicativo de referência.

Segurança:

- mostrar a senha mascarada;
- armazenar a senha com `keyring` no Gerenciador de Credenciais do Windows;
- nunca escrever senha em JSON ou log;
- recomendar senha de aplicativo para provedores que exigem autenticação em duas etapas.

## 4. Requisitos não funcionais

- Windows 10/11 e Python 3.11 ou 3.12.
- Interface responsiva em 1366×768 e 1920×1080.
- Inicialização alvo inferior a 5 segundos em máquina comum.
- Prévia estável em 24 FPS ou mais quando a câmera permitir.
- Nenhuma operação SMTP, som ou leitura pesada deve bloquear a thread da interface.
- Encerramento deve liberar `VideoCapture`, cancelar callbacks e aguardar workers curtos.
- Logs com rotação, sem senha e sem e-mail completo.
- Funcionamento local de captura mesmo quando a internet estiver indisponível.

## 5. Dependências propostas

- `customtkinter`: interface moderna.
- `opencv-python`: captura e composição de vídeo.
- `Pillow`: imagens, miniaturas e conversões.
- `keyring`: credencial protegida pelo Windows.
- `pygame`: reprodução assíncrona do WAV.
- biblioteca padrão: `smtplib`, `email.message`, `threading`, `queue`, `json`, `logging`, `pathlib`.
- `email-validator` (opcional, recomendado): validação robusta do destinatário.
- `pyinstaller`: geração futura do `.exe`.

## 6. Fases de execução

### Fase 1 — Fundação

- Criar estrutura de pastas, `requirements.txt` e arquivo principal.
- Implementar preferências, logging e descoberta de recursos.
- Validar câmera e renderização básica.

### Fase 2 — Composição visual

- Implementar resize/crop consistente.
- Implementar posição, zoom, máscara e moldura.
- Criar galeria de fundos e persistência da seleção.

### Fase 3 — Experiência de captura

- Implementar máquina de estados.
- Implementar contagem animada, flash e som.
- Salvar foto final e tela de revisão.

### Fase 4 — E-mail e configurações

- Implementar formulário SMTP e armazenamento com `keyring`.
- Implementar teste de envio.
- Implementar fila de envio e retorno seguro para a interface.

### Fase 5 — Robustez e entrega

- Executar testes funcionais e de falhas.
- Medir fluidez e uso de CPU/memória.
- Empacotar com PyInstaller incluindo assets.
- Testar em outra conta/máquina Windows.

## 7. Critérios de aceite

- A prévia da câmera abre sem travar a interface.
- É possível escolher qualquer uma das imagens disponíveis na pasta local configurada.
- Posição e zoom podem ser alterados e restaurados.
- Um clique inicia contagem animada; cliques extras são ignorados.
- A foto final corresponde visualmente à prévia.
- `nudge.wav` toca exatamente na captura.
- A foto é salva mesmo quando o envio falha.
- Remetente e senha podem ser configurados na interface.
- A senha não aparece em `settings.json` nem em logs.
- O envio ocorre sem congelar vídeo/animações.
- O usuário recebe retorno claro de sucesso ou erro.
- Fechar o aplicativo libera a câmera e encerra sem processo órfão.

## 8. Decisões a validar durante a implementação

- Se as imagens da pasta `Camera` são fundos completos, molduras transparentes ou uma mistura dos dois tipos.
- Qual provedor SMTP será usado em produção e se exige senha de aplicativo.
- A moldura permanece ativa após a captura e só muda por escolha manual do operador.
- Texto do assunto e corpo do e-mail, identidade visual e política de privacidade do museu.
