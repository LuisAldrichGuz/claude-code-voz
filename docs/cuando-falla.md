# Cuando falla

Lo primero es **`voz doctor`**: revisa todo lo de esta guia y arregla lo que se puede
arreglar solo. Casi siempre ahi se acaba el problema.

    voz doctor      revisa y repara; una linea por revision

Esa misma pasada corre sola en los dos momentos en que las cosas se rompen -al arrancar
la sesion (o tras `systemctl restart voz`) y al encender con SUPER+ALT+M5-, pero en
silencio: lo que arregla lo deja en `voz log` y solo avisa en pantalla si algo quedo roto
SIN arreglo. Lo que no sabe arreglar solo son las tres cosas que decide el usuario:
aprobar la carpeta en el Claude maestro, los binds de la M5 y los hooks de Claude Code.

Cada averia vive en `voz/salud/revisiones.py`, una funcion que la reconoce y otra que la
repara. Un sintoma nuevo se agrega ahi y entra solo en las tres pasadas.

Si el doctor dice que todo esta bien y aun asi falla, lo que sigue son estas dos ordenes:
dicen mas que cualquier sospecha.

    voz estado      # demonio vivo, asistente encendido, si esta hablando
    voz log         # que oyo, que entrego y por que NO entrego

El registro nombra el motivo de cada descarte (`no se oyo nada`, `soltaste demasiado
rapido`, `TTS: ...`, `SIN cancelacion de eco`). Si algo no llego, ahi dice por que.

---

## Digo "Claudio" y no pasa nada

`voz log` lo dice todo, porque cada frase deja su duracion, su fuerza y lo que entendio:

    [ 2.8s fuerza 0.30 sin tecla] oido: 'Claudio prueba'

- **`oido: ''` con fuerza alta** - se oye bien pero whisper devuelve vacio: casi siempre
  es que el servidor esta caido. Lo apaga el vigilante para soltar la VRAM y lo arranca
  cualquiera de los dos caminos; comprueba con `voz estado` y el log (`whisper no arranco`).
- **`sin el nombre, no se entrego`** - se oyo, pero no se reconocio "Claudio" en la frase.
  Mira como lo transcribio y, si es una forma nueva, agregala a `VARIANTES`.
- **Ninguna linea** - no esta llegando audio: ver la seccion del microfono, abajo.

## Aprieto la tecla y no pasa nada

En orden:

1. `voz estado` - si dice apagado, enciendelo con **SUPER+ALT+M5**. Apagado es apagado:
   el microfono esta cerrado y la tecla no hace nada, a proposito. **Recien iniciada la
   sesion siempre esta apagado**: el demonio arranca asi de fabrica.
2. La tecla llama a `bin/voz-tecla`, que necesita el pid en
   `$XDG_RUNTIME_DIR/voz/daemon.pid`. Sin demonio, sale sin hacer ruido:
   `systemctl --user restart voz`.
3. Comprueba el enlace a mano - `voz-tecla habla`, hablas, `voz-tecla calla` - y mira el
   log. Si asi si funciona, lo que fallo es el bind de Hyprland (`bindd` para apretar,
   **`bindrd`** para soltar, en `~/.config/hypr/bindings.conf`).

## Me corta el principio de la frase

Hay `COLCHON` segundos de margen hacia atras justo para eso. Si sigue faltando, subelo en
`voz/control/config.py`. Lo que NO se puede hacer es abrir el microfono al apretar:
`parec` tarda metro y medio de segundo en arrancar y ahi si se pierde la frase entera.

Medir cuanto se esta capturando de verdad:

    voz-tecla habla; sleep 6; voz-tecla calla   # el log debe decir ~6.5s

## No transcribe nada / dice "no se oyo nada"

Es el filtro de audio mudo (`MUDO`), y esta a proposito: con silencio whisper no devuelve
vacio, se inventa un "Gracias." que acabaria en el chat como una orden. Si sale con voz de
verdad, el microfono no esta captando:

    pactl list short sources          # voz_sin_eco debe estar RUNNING
    pactl get-source-mute <fuente>    # venia muteado de fabrica

Nunca se graba de `@DEFAULT_SOURCE@`: en esta maquina el default se va solo al `.monitor`
de la salida y entonces se graba lo que suena por las bocinas. Aparenta funcionar -
transcribe lo que suena - mientras ignora al usuario. Lo elige `microfono.fuente_real()`.

## Se oye a si mismo, o se cuela el juego

Hubo cancelacion de eco de PipeWire y **se quito**: EasyEffects saca su salida al sink por
defecto, asi que poniendo el cancelador delante se mandaba el audio a si mismo y la tarjeta
se quedaba muda - todo se veia bien en los medidores y no salia una nota.

Con la tecla ya no hace falta: el microfono solo guarda lo que entra mientras la aprietas.
Si algun dia se vuelve a montar, `microfono.fuente_real()` ya prefiere `voz_sin_eco`, pero
el cancelador tiene que quedar DESPUES de EasyEffects, nunca antes.

## El punto se queda encendido y el agente ya acabo

Si interrumpes a Claude Code con **Escape**, el hook que apaga el aviso nunca corre - solo
se dispara cuando el turno termina bien. El demonio mira la pantalla del agente cada 2 s y
lo apaga cuando vuelve a su prompt (`sesion.listo()`). Si aun asi se queda pegado:
`systemctl --user restart voz`.

## No me contesta en voz

`voz log` trae una linea `TTS:` por cada turno con el motivo exacto; Claude Code se traga
la salida del hook con `2>/dev/null`, asi que sin esa linea no hay forma de saber nada.

- `callado, el micro esta apagado` - es a proposito.
- Ninguna linea - la sesion no es el maestro. Solo habla el Claude Code que vive en la
  ventana de tmux `voz`; los que manejas por teclado se quedan callados a proposito.
- `piper no pudo hablar` - falta `.venv/bin/piper` o la voz `.onnx`.
- **Habla con dos voces distintas** (los "ahí voy" con una y las respuestas con
  otra): cambiaste de voz con `voz motor` y el demonio sigue con la de antes en
  memoria. `systemctl --user restart voz`, o `voz doctor`, que ya lo detecta.

**Lee solo un pedazo.** Lleva marca de lo ya leido (`leido.json`) y espera a que el
transcript deje de crecer: el texto final del turno se escribe TARDE, asi que leer "el
ultimo bloque" dejaba fuera la respuesta completa.

## Se fue el sonido bueno o la barra de volumen

Efecto colateral de reiniciar PipeWire:

    omarchy-restart-swayosd                      # vuelve la UI de volumen
    easyeffects --gapplication-service &         # vuelven los presets de audio

`swayosd-server` queda **vivo pero desconectado**, por eso despista: sigue contestando
avisos y las teclas de volumen no pintan nada. EasyEffects simplemente se cae, y su
autostart solo corre al entrar a la sesion.

## Desarmar todo

    systemctl --user stop voz voz-indicador
    omarchy-restart-swayosd && easyeffects --gapplication-service &

El hook que lee en voz alta se quita del bloque `Stop` de `~/.claude/settings.json`, y los
binds de la M5 de `~/.config/hypr/bindings.conf`.
