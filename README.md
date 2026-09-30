# voz — háblale a Claude Code, y que te conteste

Asistente de voz **100 % local** para [Claude Code](https://claude.com/claude-code) en
Linux/Wayland. Le hablas, te escucha, y su respuesta te la lee en voz alta. Nada de audio
sale de la máquina: transcribe con whisper.cpp en la GPU y habla con piper.

> **Solo Linux con Wayland.** No es multiplataforma y no va a serlo: se apoya en
> layer-shell del compositor para el indicador, en PipeWire/PulseAudio para el audio, en
> tmux para la sesión del agente y en `wtype` para teclear. En Windows o macOS no corre.
> Probado en Hyprland; en otro compositor Wayland con soporte de layer-shell debería ir.

No teclea en la ventana que tengas enfrente: lo dictado va a un Claude Code «maestro» que
vive en una sesión de tmux, así que le llegas estés donde estés — en el navegador, en un
juego o en otra terminal.

![oyéndote](docs/img/verde-oyendo.png)

---

## Cómo se le habla

Dos formas, la que acomode:

| | |
|---|---|
| **Manos libres** | empiezas la frase con **«Claudio»** y hablas |
| **Con tecla** | mantienes una tecla apretada y dictas sin nombrarlo |

Todo lo que digas de corrido sale como **un solo mensaje**. Las frases se cortan por cómo
funciona el reconocimiento, no porque hayas terminado: mandando cada pedazo por separado,
una instrucción larga llegaba partida e interrumpía a la anterior.

Y la conversación es **uno a uno**: desde que se manda tu mensaje hasta que termina de
leerte la respuesta, el micrófono no graba nada. Ni tu voz ni lo que suene en el cuarto.

## Un punto, y todo el estado

Lo único que vive en pantalla es un punto arriba a la derecha. Sale cuando te atiende y se
desvanece; nada de notificaciones tapando lo que lees.

| | Estado |
|---|---|
| ![](docs/img/verde-oyendo.png) | **verde** — te reconoció el nombre y te está grabando |
| ![](docs/img/cian-respiro.png) | **cian** — te callaste; unos segundos por si sigues, es el mismo mensaje |
| ![](docs/img/ambar-pensando.png) | **ámbar** — transcribiendo, o el agente trabajando |
| ![](docs/img/morado-hablando.png) | **morado** — leyendo la respuesta; el micrófono está cerrado |

El verde **solo** se enciende después de reconocerte el nombre. Encenderlo con cualquier
voz que el detector oyera era mentir: con alguien hablando de fondo parecía que te estaba
atendiendo, y no le hacía caso a nadie.

## Qué usa

| Pieza | Para qué |
|---|---|
| [whisper.cpp](https://github.com/ggerganov/whisper.cpp) (`large-v3-turbo`, CUDA) | pasar tu voz a texto; suelta la VRAM cuando no se usa |
| [Silero VAD](https://github.com/snakers4/silero-vad) | saber si lo que suena es una persona hablando, no medir volumen |
| [piper](https://github.com/rhasspy/piper) | leer la respuesta en voz alta |
| GTK4 + layer-shell | el punto en pantalla, sin depender del daemon de notificaciones |
| tmux | donde vive el Claude Code maestro |

## Cómo sabe si el agente sigue trabajando

Esto es lo que más costó. Mirando la pantalla de tmux se falla siempre: entre una
herramienta y la siguiente el prompt reaparece un instante y se da el turno por terminado
— el punto se apaga a media faena y parece que no hizo caso.

Claude Code lo dice él mismo, por dos vías que se complementan:

- **Sus hooks.** `UserPromptSubmit` enciende una marca y `Stop` la apaga. Instantáneo.
- **`claude agents --json`.** La vía documentada para preguntarle por sus sesiones;
  devuelve `busy`, `waiting` o `idle`. Se consulta cada dos segundos como red, porque si
  interrumpes al agente con `Esc` el hook de fin nunca llega a correr.

El hook de lectura también decide **qué sesión habla**: solo la que vive en la ventana de
tmux del maestro. Los hooks son globales, así que sin eso cualquier Claude Code abierto
leería sus respuestas en voz alta y acabarían hablando todos encima.

## Instalación

**Requisitos:** Linux con Wayland (compositor con layer-shell), Python 3.11+, y una GPU
NVIDIA para whisper — funciona en CPU, bastante más lento. Paquetes: `tmux`, `grim`,
`wtype`, GTK4 con `gtk4-layer-shell`, y `parec`/`paplay` de PipeWire o PulseAudio.

```bash
git clone <este-repo> voz && cd voz
python -m venv .venv && .venv/bin/pip install onnxruntime numpy piper-tts

# whisper.cpp con CUDA, y el modelo
git clone https://github.com/ggerganov/whisper.cpp ../voz-whisper
cmake -B ../voz-whisper/build -S ../voz-whisper -DGGML_CUDA=1 && cmake --build ../voz-whisper/build -j
../voz-whisper/models/download-ggml-model.sh large-v3-turbo

# la voz de piper (cualquiera de rhasspy/piper-voices)
mkdir -p voces && curl -L -o voces/es_MX-claude-high.onnx <url-del-modelo>

bin/voz demonio        # o instálalo como servicio de usuario
```

Luego, en `~/.claude/settings.json`, los dos hooks:

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command",
      "command": "python3 ~/voz/voz/claude_code/marca_turno.py 2>/dev/null || true" }] }],
    "Stop": [{ "hooks": [{ "type": "command",
      "command": "python3 ~/voz/voz/claude_code/lee_respuesta.py 2>/dev/null || true",
      "async": true, "timeout": 120 }] }]
  }
}
```

Y la tecla, en tu compositor. En Hyprland, apretar y soltar:

```
bind  = , code:156, exec, ~/voz/bin/voz-tecla habla
bindr = , code:156, exec, ~/voz/bin/voz-tecla calla
bind  = SUPER ALT, code:156, exec, ~/voz/bin/voz toggle
```

**Arranca apagado.** Al entrar a la sesión el demonio se levanta, pero con el micrófono
cerrado y sin subir whisper a la GPU: nadie quiere que una máquina recién encendida esté
escuchando el cuarto. Se enciende con `SUPER+ALT+M5` (o `voz on`) y ahí sí se destapa el
micro y sube el modelo.

El nombre con el que se le llama, los umbrales y los tiempos están todos en
[`voz/control/config.py`](voz/control/config.py).

## Comandos

```
voz habla | calla     empieza y cierra el dictado (los llama la tecla)
voz toggle | on | off enciende o apaga el asistente entero
voz estado            en qué anda
voz doctor            revisa todo y arregla lo que pueda
voz log | oir         lo que entendió, y en vivo
voz ver | agentes     abre el Claude maestro, o lista los que hay
voz decir "texto"     léelo en voz alta
```

## Cuando algo falla

Antes que nada, **`voz doctor`**: revisa las diez averías conocidas y arregla las que se
pueden arreglar solas (micrófono muteado, isla caída, whisper pegado, marcas pegadas,
maestro muerto, swayosd desconectado de PipeWire). Esa misma pasada corre sola **al
arrancar** la sesión y **cada vez que lo enciendes** con SUPER+ALT+M5, calladita: lo que
repara queda en `voz log` y solo avisa en pantalla si algo quedó roto sin arreglo.

[`docs/cuando-falla.md`](docs/cuando-falla.md) es la guía de reparación por síntoma. El
registro (`voz log`) nombra el motivo de **cada** descarte, que fue la lección más cara de
todas: callarse cuando algo no se entrega hace parecer que el programa está descompuesto.

## Estructura

```
voz/escucha/        el micrófono, el detector de voz y la palabra de activación
voz/transcripcion/  cliente de whisper-server
voz/agentes/        la sesión tmux donde vive el Claude Code maestro
voz/dictado/        teclear en la ventana enfocada (solo si dices "escribe")
voz/habla/          piper y la limpieza de markdown para que suene bien
voz/control/        configuración, estado y el demonio (una máquina de estados)
voz/salud/          el doctor: las averías conocidas y cómo se arreglan solas
voz/indicador/      el punto en pantalla (GTK4 layer-shell)
voz/claude_code/    los dos hooks: marcar el turno y leer la respuesta
```

## Licencia

MIT. Los modelos que descargues traen la suya.
