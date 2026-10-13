# Checklist de implementação

## Preparação

- [ ] Criar `camera_museu.py` e `requirements.txt`.
- [ ] Criar `assets/audio`, `assets/fundos`, `assets/icones`, `config`, `fotos` e `logs`.
- [ ] Copiar o som de captura escolhido para `assets/audio/nudge.wav`.
- [ ] Documentar como criar e ativar ambiente virtual.
- [ ] Adicionar `.gitignore` para ambiente, logs, fotos e configurações locais.

## Núcleo

- [ ] Implementar `SettingsStore` e padrões.
- [ ] Implementar logging rotativo com dados mascarados.
- [ ] Implementar abertura, troca e liberação da câmera.
- [ ] Implementar preview responsivo com limite de FPS.
- [ ] Implementar compositor único para preview e captura.

## Interface

- [ ] Reproduzir a organização principal observada no EXE.
- [ ] Implementar fullscreen, redimensionamento e atalhos.
- [ ] Implementar galeria de fundos e próximo/anterior.
- [ ] Implementar painel de ajustes com setas, zoom e reset.
- [ ] Implementar configurações completas do remetente.

## Captura

- [ ] Implementar estados e bloqueio de clique duplo.
- [ ] Implementar 3–2–1 animado com `after()`.
- [ ] Implementar flash e som assíncrono.
- [ ] Salvar arquivo em resolução final e pasta por data.
- [ ] Implementar tela de revisão e nova tentativa.
- [x] Manter a moldura atual após cada captura.

## E-mail

- [ ] Validar e mascarar destinatário.
- [ ] Implementar SSL e STARTTLS.
- [ ] Armazenar senha com `keyring`.
- [ ] Implementar “Testar envio” sem congelar a interface.
- [ ] Implementar worker, fila de retorno e reenvio.
- [ ] Criar assunto e corpo configuráveis.

## Testes manuais mínimos

- [ ] Câmera ausente, ocupada e reconectada.
- [ ] Janela 1366×768, 1920×1080 e fullscreen.
- [ ] Cada um dos quatro arquivos atuais da pasta de fundos.
- [ ] Fundo/moldura inválido ou removido durante a execução.
- [ ] Capturas rápidas repetidas.
- [ ] Som ausente e dispositivo de áudio indisponível.
- [ ] E-mail vazio, inválido e válido.
- [ ] Senha incorreta, sem internet e timeout SMTP.
- [ ] Foto salva quando o envio falha.
- [ ] Senha ausente do JSON e dos logs.
- [ ] Encerramento durante preview, contagem e envio.

## Entrega

- [ ] Executar teste de fumaça do `.py` em ambiente limpo.
- [ ] Criar build PyInstaller.
- [ ] Validar recursos e credenciais no executável.
- [ ] Testar em outro computador Windows.
- [ ] Registrar versão, data e instruções de operação.
