# Arquitetura proposta

## Estratégia

A primeira versão será entregue em um único `camera_museu.py`, como solicitado, mas organizada internamente em classes pequenas. Isso facilita gerar um único executável e evita um arquivo procedural difícil de manter.

## Classes e responsabilidades

### `CameraMuseuApp`

- cria a janela e coordena as telas;
- mantém a máquina de estados;
- agenda a prévia com `after()`;
- recebe resultados das filas de trabalho;
- realiza o encerramento ordenado.

### `CameraService`

- abre/fecha `cv2.VideoCapture`;
- seleciona dispositivo e resolução;
- devolve cópia segura do frame mais recente;
- detecta falha e tenta reconexão controlada.

### `ImageComposer`

- calcula `cover`/`contain` sem deformar imagens;
- aplica zoom e deslocamento;
- usa canal alfa de PNG;
- gera prévia e foto final com a mesma transformação.

### `BackgroundRepository`

- pesquisa extensões aceitas;
- une pasta externa e pasta local;
- cria/cacheia miniaturas;
- controla item atual, próximo e anterior.

### `CaptureController`

- executa o cronômetro por callbacks;
- controla flash e som;
- cria nome de arquivo e salva de forma atômica;
- impede duas capturas simultâneas.

### `EmailService`

- monta mensagem MIME com anexo;
- conecta via SSL ou STARTTLS;
- envia em worker de segundo plano;
- traduz erros técnicos em mensagens úteis.

### `SettingsStore`

- lê/grava preferências não sensíveis em JSON;
- lê/grava a senha usando `keyring`;
- valida caminhos, porta e valores numéricos;
- aplica padrões quando a configuração está ausente ou inválida.

## Máquina de estados

```text
INICIALIZANDO
     |
     v
PRONTO ---> CONTAGEM ---> CAPTURANDO ---> REVISAO ---> ENVIANDO
  ^            |              |              |             |
  |            `-- cancelar --'              `-------------'
  |                                                        |
  `---------------- sucesso/falha/novo atendimento <-------'

Qualquer estado pode ir para ERRO_RECUPERAVEL sem encerrar o programa.
```

Somente `PRONTO` aceita nova captura. O botão e o atalho de teclado refletem o estado atual.

## Concorrência

- Thread principal: widgets, animações, preview e leitura das filas.
- Worker de e-mail: conexão SMTP e envio.
- Opcionalmente, thread de câmera se a leitura do driver bloquear; a interface consome apenas o último frame.
- Comunicação por `queue.Queue`; workers nunca alteram widgets diretamente.
- O som é reproduzido pelo mixer em modo não bloqueante.

## Persistência

Exemplo de `config/settings.json`:

```json
{
  "sender_email": "",
  "sender_name": "Museu",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 465,
  "smtp_security": "ssl",
  "camera_index": 0,
  "camera_width": 1920,
  "camera_height": 1080,
  "camera_scale": 1.0,
  "camera_offset_x": 0,
  "camera_offset_y": 0,
  "countdown_seconds": 3,
  "mirror_preview": true,
  "fullscreen": true,
  "background_folder": "assets/fundos",
  "photo_folder": "fotos",
  "selected_background": ""
}
```

A senha fica no serviço `CameraMuseuDEN`, chaveada pelo e-mail remetente no cofre do Windows.

## Composição da imagem

1. Carregar arte e identificar presença de alfa.
2. Ajustar arte ao canvas pelo modo configurado.
3. Calcular retângulo da câmera a partir de centro, escala e deslocamento.
4. Aplicar recorte circular/retangular ou a máscara alfa da arte.
5. Compor em memória na resolução final.
6. Redimensionar uma cópia para a prévia; nunca salvar a miniatura.

## Tratamento de falhas

- Câmera ocupada: informar e oferecer “Tentar novamente”.
- Frame vazio: manter último frame por curto período e reconectar.
- Fundo inválido: ignorar arquivo e avançar para o próximo válido.
- Som ausente: capturar normalmente e registrar aviso.
- Sem rede/autenticação: manter foto salva e habilitar reenvio.
- Destinatário inválido: não iniciar contagem.
- Falha ao salvar: não iniciar envio e mostrar o caminho/causa amigável.

## Empacotamento futuro

Gerar um executável Windows sem console via PyInstaller, incluindo `assets/`. Preferir pasta de distribuição (`--onedir`) durante testes por iniciar mais rápido; avaliar `--onefile` somente na entrega final.
