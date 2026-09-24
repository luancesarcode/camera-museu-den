<div align="center">
  <img src="assets/icones/camera_museu.png" alt="Logo Camera Museu DEN" width="150">

  <h1>Camera Museu DEN</h1>

  <p>Captura e compartilha fotografias do museu com molduras personalizadas.</p>

  <p>
    <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-blue.svg">
    <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB">
    <img alt="Windows" src="https://img.shields.io/badge/OS-Windows-0078D6">
    <img alt="Release v1.0.0" src="https://img.shields.io/badge/Release-v1.0.0-2ea44f">
  </p>
</div>

---

O **Camera Museu DEN** é um aplicativo desktop para fotografias do museu. Ele oferece visualização da câmera ao vivo, molduras, contagem regressiva, galeria local e envio opcional por e-mail.

## Recursos

- Pré-visualização e captura pela câmera
- Molduras e fundos personalizados
- Contagem regressiva animada e som de captura
- Galeria e salvamento local das fotos
- Envio opcional por SMTP em segundo plano
- Senha de aplicativo guardada no Gerenciador de Credenciais do Windows

## Baixar

Baixe `CameraMuseuDEN.exe` em [Releases](../../releases/latest). No Windows, abra o executável para iniciar o aplicativo. O Windows pode exibir um aviso para aplicativos sem assinatura digital; nesse caso, confirme que baixou o arquivo da página de Releases deste repositório.

## Executar pelo código-fonte

Requer Windows e Python 3.12 ou superior.

```powershell
python -m pip install -r requirements.txt
python camera_museu.py
```

Para gerar o executável:

```powershell
.\GERAR_EXE.bat
```

## Configurar e-mail

O envio de fotos é opcional. Configure o remetente e o servidor SMTP nas opções do aplicativo. Para Gmail com autenticação em duas etapas, use uma senha de aplicativo. A senha fica no Gerenciador de Credenciais do Windows e não é salva no arquivo de configurações.

## Privacidade

As fotos e os registros locais ficam no computador onde o aplicativo é executado. Não envie arquivos pessoais de configuração, fotos ou credenciais ao repositório.

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
