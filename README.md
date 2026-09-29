# voz — dictado y asistente de voz local

Todo corre en esta maquina: nada de audio sale a internet.

Dos formas de hablarle, la que te acomode:

- **Manos libres**: empiezas la frase con **"Claudio"** y sigues hablando.
- **Con la tecla**: mantienes la **M5** apretada y dictas lo que quieras sin nombrarlo.

- **Oir**: whisper.cpp con CUDA (modelo `large-v3-turbo` en la RTX 5070). Sin usarse un
  rato suelta sus ~2 GB de VRAM y vuelve al apretar.
- **Escribir**: `wtype` teclea en la ventana enfocada, asi funciona con Claude Code,
  el navegador o donde sea.
- **Hablar**: piper con la voz `es_MX-claude-high`.

### Como se comporta sin la tecla

Dices **"Claudio"** y a partir de ahi:

- **verde** mientras te oye;
- **cian** los dos segundos de respiro cuando callas: mientras este cian sigues en el
  MISMO mensaje, puedes tomar aire y seguir;
- se manda cuando te callas de verdad.

Todo lo que digas de corrido sale como **un solo mensaje**. Las frases se cortan a los
ocho segundos por como funciona whisper, no porque hayas terminado: mandando cada pedazo
por separado, una instruccion larga llegaba partida e interrumpia a la anterior.

**Hace falta el nombre para empezar.** No hay ventanas, ni sesiones que se
queden abiertas, ni respiros: eso fue lo que dejaba entrar los dialogos de un juego
durante horas, porque bastaba con que algo abriera la sesion una vez para que todo lo
que sonara despues entrara solo.

Y el nombre es "Claudio" y no "Claude" porque whisper transcribe en espanol: "Claude" le
salia "Claro" o "Cloud", y "Claro" es palabra comun. Para dictar largo sin repetirlo en
cada frase esta la tecla.

## Como se usa

| Accion | Como |
|---|---|
| Hablarle sin tocar nada | empieza la frase con **"Claudio"** |
| Dictar largo | **manten** la M5 apretada, habla, sueltala |
| A donde va | a tu Claude maestro en tmux, estes en la ventana que estes |
| Dictar en otro lado | empieza con "escribe": va a la ventana que tengas enfrente |
| Interrumpir la lectura | pica la pastilla |
| Apagarlo en una junta | **SUPER+ALT+M5**: sale el aviso "Chat de voz desactivado" |
| Ver al maestro | `voz ver` · `voz agentes` los lista |
| Ver que entendio | la isla · `voz log` · `voz oir` |

Apagado, el microfono se cierra de verdad y whisper suelta la VRAM. La tecla no hace nada.

### Lo que dice el punto

Es lo unico que se ve en pantalla, arriba a la derecha:

| Color | Que pasa |
|---|---|
| gris claro | listo; di "Claudio" o aprieta la tecla |
| cian | te callaste: dos segundos por si sigues, es el mismo mensaje |
| verde | tienes la tecla apretada, te esta grabando |
| ambar | transcribiendo, o el agente trabajando |
| morado | leyendo en voz alta |
| gris oscuro | apagado; la tecla no hace nada |

## Estructura

    voz/escucha/        el microfono (y elegir la fuente sin eco)
    voz/transcripcion/  cliente de whisper-server
    voz/agentes/        la sesion tmux donde viven los Claude Code
    voz/dictado/        teclea en la ventana enfocada (solo si dices "escribe")
    voz/habla/          piper + limpieza de markdown para que suene bien
    voz/control/        configuracion, estado y el demonio
    voz/indicador/      la isla en pantalla (GTK4 layer-shell, sin mako)
    voz/claude_code/    hook que lee en voz alta la respuesta de Claude Code
    docs/cuando-falla.md  reparacion por sintoma: leelo antes de tocar nada

Los ajustes (umbrales del micro, nombre, tiempos) estan todos en
`voz/control/config.py`.


## Trampas que ya costaron caro

1. **Whisper tiene que estar encendido pase lo que pase.** El vigilante lo apaga tras un
   rato sin uso para soltar la VRAM, y durante un tiempo solo lo volvia a arrancar la
   tecla: todo lo que se oia sin ella llegaba a un servidor caido y volvia como cadena
   vacia. Se oia perfecto, la frase se cortaba bien, y no pasaba absolutamente nada.
2. **Sin tecla, el nombre se busca en TODA la frase.** El detector abre la frase con el
   ruido del cuarto y lo que dices se pega detras, asi que el nombre casi nunca cae en
   las primeras palabras.
3. **Silero v5 necesita el contexto del frame anterior** (64 muestras pegadas delante) o
   contesta que no hay nadie hablando: con voz clarisima daba 0.16 donde debe dar 1.00.
4. **Dos hilos no pueden escribir el mismo archivo temporal.** Uno renombraba y al otro
   le estallaba FileNotFoundError, que se llevaba el hilo del microfono entero; el
   demonio seguia "vivo" y el microfono "encendido", sordo y sin decir nada. Ahora cada
   hilo usa el suyo y, si se cae, se levanta solo y lo deja escrito.
5. **La tecla no puede lanzar Python.** `voz habla` arrancaba un interprete entero, unos
   300 ms, y ese arranque se come el principio de la frase. La tecla llama a
   `bin/voz-tecla`, que es bash y solo manda la senal: 3 ms.
6. **El microfono se deja abierto, pero solo se GUARDA con la tecla apretada.** Abrirlo
   justo al apretar se probo primero y `parec` tardaba metro y medio de segundo en
   arrancar. Ademas hay `COLCHON` segundos de margen hacia atras, por si aprietas tarde.
   Apagando el asistente el microfono se cierra de verdad: en una junta eso es lo unico
   que vale, no confiar en que el programa decida bien.
7. **Un audio mudo no se manda.** Whisper no devuelve vacio con silencio: se inventa un
   "Gracias." o un "Subtitulos por la comunidad", y eso acabaria en el chat como una
   orden. Por eso `MUDO`.
8. **Poner un cancelador de eco delante de EasyEffects lo mete en un bucle.**
   EasyEffects saca su salida al sink por DEFECTO; si ese es el cancelador, se manda el
   audio a si mismo y la tarjeta se queda sin nada - suena todo bien en los medidores y
   no sale una nota. Se quito: con la tecla no hace falta, porque el microfono solo
   guarda mientras la aprietas.
9. **Nunca grabar de `@DEFAULT_SOURCE@`.** En esta maquina el default se va solo al
   `.monitor` de la salida: entonces se graba lo que suena por las bocinas y el
   asistente *aparenta* funcionar mientras te ignora. `microfono.fuente_real()` elige
   `voz_sin_eco`, y si no esta, una entrada ALSA de verdad.
10. **El aviso de que el agente trabaja se apaga mirando su pantalla**, no esperando al
   hook: si interrumpes a Claude Code con Escape ese hook nunca corre y el punto se
   queda encendido para siempre.
11. **La isla no vive en pantalla.** Sale SOLO mientras te atiende -grabando,
   transcribiendo, leyendo- y se desvanece. Nada de asomar a cada cambio de estado: eso
   dejaba un punto gris apareciendo sin que hubieras tocado nada. Encender y apagar lo
   dice el OSD de Omarchy, el mismo del volumen. Y nada de notificaciones del sistema:
   interrumpen encima de lo que estas leyendo.
12. **La ventana tiene que ser transparente** (`window { background: transparent }`) o el
   cuadro gris de GTK asoma por detras de las esquinas redondeadas. Y para que encoja al
   quitarle el texto hay que pedirle el tamano minimo a mano; el label necesita
   `width_chars` o se aplasta a dos letras por renglon.
13. **Nunca escribirle a un agente que no esta en su prompt.** Si esta en un dialogo, el
   Enter del dictado contesta ESE dialogo: asi murio el primer maestro, con el Enter
   cayendo sobre "No, exit". `sesion.listo()` se revisa antes de cada envio.
14. **La ventana de tmux corre un shell, no `claude` directo.** Si Claude se cae, la
    ventana sobrevive y se puede ver que paso.
15. **El hilo que lee el microfono no puede hacer NADA lento.** Transcribir y entregar
    ahi dentro dejaba al microfono llenandose por detras: cada frase que llegaba era la
    anterior. Van en hilos aparte (`graba` / `trabaja` / `vigila`).
16. **Solo habla el maestro.** El hook esta puesto global, asi que sin comprobar en que
    sesion corre, CUALQUIER Claude Code abierto lee sus respuestas en voz alta.
17. **Si el agente esta ocupado, dilo.** Claude Code encola lo que le llega; sin
    mostrarlo, parece que el asistente contesta lo del mensaje anterior.
