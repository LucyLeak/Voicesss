# Voicesss

Detector de voz em Python para transcrever fala em portugues e normalizar
auto-referencias no feminino.

Ele foi desenhado para ser portatil: a captura de audio, a transcricao e a
normalizacao linguistica ficam separadas, entao voce pode trocar o microfone, o
modelo ou a lista de termos sem mexer no resto do aplicativo.

## O que ele faz

- Detecta fala pelo microfone usando VAD.
- Transcreve com `faster-whisper`, localmente.
- Transcreve arquivos de audio.
- Corrige auto-referencias comuns para o feminino, como `eu estou cansado` para
  `eu estou cansada`, `eu mesmo` para `eu mesma` e `muito obrigado` para
  `muito obrigada`.
- Aceita um lexico JSON para adaptar palavras ao seu jeito de falar.

Nenhum sistema de fala consegue prometer transcricao perfeita em qualquer
ambiente. Para chegar mais perto disso, use um microfone limpo, fale perto da
fonte, evite ruido e escolha um modelo maior quando a maquina aguentar.

## Instalacao

No Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[all]"
```

Na primeira transcricao, o modelo escolhido sera baixado automaticamente.

## Comando direto no PowerShell

Depois de instalar a `.venv`, registre os comandos no seu perfil do PowerShell:
O instalador tambem cria atalhos `.cmd`, entao o comando funciona mesmo sem
ativar a `.venv`.

```powershell
.\scripts\install-powershell-command.ps1
```

Feche e abra o PowerShell, ou rode este comando na janela atual:

```powershell
. $PROFILE.CurrentUserAllHosts
```

Depois disso, use de qualquer pasta:

```powershell
voicesss normalize "eu estou cansado"
voicesss-app
```

## Uso

Abrir o aplicativo:

```powershell
voicesss-app
```

Testar so a normalizacao:

```powershell
voicesss normalize "eu estou cansado, muito obrigado"
```

Listar microfones:

```powershell
voicesss devices
```

Mostrar todos os dispositivos de audio que o Windows reporta:

```powershell
voicesss devices --all
```

Escutar o microfone:

```powershell
voicesss listen --model small
```

Transcrever um arquivo:

```powershell
voicesss file .\audio.wav --model medium --output .\transcripts\saida.txt
```

Escolher um microfone especifico:

```powershell
voicesss listen --input-device 1
```

Na interface grafica, escolha o microfone na caixa `Microfone`, selecione o
modelo e clique em `Iniciar`. Use `Parar` para encerrar a captura.
O app transcreve quando voce faz uma pausa curta ou quando uma fala continua
por alguns segundos; ele nao mostra palavra por palavra enquanto voce ainda esta
falando.

## Personalizar palavras

Edite um JSON no formato de `config/lexicon.example.json`:

```json
{
  "complements": {
    "realizado": "realizada",
    "grato": "grata"
  },
  "self_pronouns": {
    "proprio": "própria"
  },
  "nouns": {
    "pesquisador": "pesquisadora"
  }
}
```

Depois use:

```powershell
voicesss listen --lexicon .\config\lexicon.example.json
```

## Modelos recomendados

- `tiny`: menor latencia em CPU; e o padrao do app.
- `base`: bom ponto de partida em CPU.
- `small`: melhor qualidade, mas ja pode parecer lento em CPU.
- `medium`: melhor qualidade, mais pesado.
- `large-v3`: melhor para qualidade, mas exige mais memoria e tempo.

Se tiver GPU NVIDIA configurada, teste:

```powershell
voicesss listen --device cuda --compute-type float16 --model medium
```

Em GPU integrada AMD, use CPU. O motor atual (`faster-whisper`) aceita `cpu`,
`cuda` ou `auto`; `cuda` e para NVIDIA. O app usa CPU com `int8` e threads
automaticas por padrao, que costuma ser o caminho mais estavel em AMD/Intel.

Verificar ROCm/HIP no ambiente atual:

```powershell
voicesss rocm
```

## Desenvolvimento

Rodar testes:

```powershell
python -m unittest discover
```
