#!/usr/bin/env python3
"""Hook `PostToolUse`: leer lo que el agente va diciendo, sin esperar al final del turno.

Con solo el hook `Stop`, un turno de cinco minutos es cinco minutos de silencio y luego
todo de golpe: no hay forma de saber si esta trabajando o si se colgo, salvo ir a mirar
su terminal. Esto lee cada bloque de texto en cuanto aterriza en el transcript, o sea
justo cuando el agente suelta un "voy a revisar esto" y se pone a ello.

Se apoya en la MISMA marca de leido que el hook del final (`leido.json`), asi que lo que
ya se dijo aqui, al cerrar el turno no se repite. Va `async` en los ajustes: leyendo en
voz alta bloquearia la siguiente herramienta hasta acabar la frase.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from voz.agentes import sesion  # noqa: E402
from voz.claude_code import leido  # noqa: E402
from voz.claude_code.lee_respuesta import _traza, pendiente  # noqa: E402
from voz.control import config, estado  # noqa: E402
from voz.habla import piper_voz, texto_hablable  # noqa: E402

ESPERA_VOZ = 60.0   # tope esperando a que calle el de antes; no dejarse colgado


def main():
    if sesion.ventana_actual() != sesion.MAESTRO:
        return 0        # los demas agentes no hablan: le pasan el recado al maestro
    if not estado.escuchando():
        return 0

    try:
        evento = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    transcript = evento.get("transcript_path", "")
    if not transcript:
        return 0

    # Varias herramientas en paralelo disparan varios hooks a la vez, y ademas esta
    # el de Stop. Sin un candado COMPARTIDO con el, dos se llevan el mismo bloque y
    # se lee dos veces. Apuntar antes de hablar: si lo cortas, no te lo repite.
    with leido.turno():
        texto, hasta = pendiente(transcript)
        if texto.strip():
            leido.apunta(transcript, hasta)
    if not texto.strip():
        return 0

    # A hablar ya fuera del candado: la frase tarda segundos y mientras suena el
    # otro hook tiene que poder apuntar lo suyo.
    limite = time.monotonic() + ESPERA_VOZ
    while config.HABLANDO.exists() and time.monotonic() < limite:
        time.sleep(0.2)

    hablado = texto_hablable.limpia(texto)
    if not hablado.strip():
        return 0
    estado.dice("responde", hablado, vida=max(8.0, len(hablado) / 12))
    if piper_voz.di(texto):
        _traza(f"avance leido ({len(hablado)} caracteres)")
    else:
        _traza("avance: piper no pudo hablar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
