# Interface e animações

## Direção visual

Manter a identidade do aplicativo observado — conteúdo fotográfico em destaque e barra superior — com acabamento mais atual:

- tema escuro neutro na barra para não competir com a arte;
- cor de destaque turquesa inspirada no executável;
- botões grandes, cantos arredondados e ícones simples;
- tipografia legível à distância;
- status sempre textual, nunca apenas por cor.

## Tela principal

```text
+------------------------------------------------------------------+
| [Tirar foto] [<] [Fundos] [>]  E-mail: [____________] [engrenagem]|
+------------------------------------------------------------------+
|                                                                  |
|                    FUNDO / MOLDURA ATIVA                          |
|                                                                  |
|                       PREVIA DA CAMERA                            |
|                                                                  |
|                  [mensagem curta de status]                       |
+------------------------------------------------------------------+
```

- A barra pode recolher após alguns segundos em modo quiosque e reaparecer ao mover o mouse.
- `F11` alterna fullscreen e `Esc` sai do fullscreen, sem fechar o app.
- `Espaço` inicia a foto quando o campo de e-mail não está em edição.
- Setas próximo/anterior comutam o fundo sem abrir uma janela.

## Cronômetro animado

- Duração padrão: 3 segundos, configurável.
- Cada número entra com escala aproximada de 70% → 115% → 100%.
- Halo circular progride ao redor do número.
- A transição usa callbacks de 16–33 ms via `after()`.
- Não usar GIF pesado nem criar widgets repetidamente.
- No zero: flash branco de 100–150 ms e reprodução de `nudge.wav`.

## Galeria de fundos

- Janela modal com grade de miniaturas cacheadas.
- Item selecionado recebe borda turquesa e marcação.
- Duplo clique ou botão “Aplicar” confirma.
- Botão “Escolher arquivo” cobre itens fora da pasta.
- Filtro por nome ajuda quando houver muitas artes.

## Configurações

Usar abas ou seções roláveis:

1. **E-mail** — remetente, senha, SMTP, segurança, testar e salvar.
2. **Câmera** — dispositivo, resolução, espelho, setas, zoom e centralizar.
3. **Experiência** — cronômetro, fullscreen e som.
4. **Pastas** — fundos, fotos e abrir pasta.

O campo de senha inicia vazio quando já existe credencial salva e mostra “Credencial armazenada”. Digitar uma nova senha substitui a anterior ao salvar.

## Estados e feedback

- Pronto: “Digite seu e-mail e toque em Tirar foto”.
- Contagem: controles desabilitados e número central.
- Salvando: indicador curto no próprio botão.
- Enviando: faixa discreta, sem bloquear novo desenho da câmera.
- Sucesso: confirmação verde com endereço mascarado.
- Falha: mensagem curta + “Tentar novamente” + “Ver detalhes”.
- Sem câmera: painel explicativo + “Reconectar câmera”.

## Desempenho visual

- Reutilizar os mesmos widgets e imagens sempre que possível.
- Cachear fundos redimensionados por `(arquivo, largura, altura)`.
- Recriar o cache apenas quando a janela estabilizar após resize.
- Limitar miniaturas e descarregar caches antigos.
- Animar apenas número, halo, flash e pequenos estados de botão.
