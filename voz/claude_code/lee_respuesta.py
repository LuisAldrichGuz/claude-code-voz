#!/usr/bin/env python3
"""Hook `Stop` de Claude Code: lee en voz alta TODO lo que contesto en el turno.

Claude Code entrega por stdin un JSON con la ruta del transcript (JSONL). De ahi se
sacan todos los bloques de texto que dijo el asistente desde tu ultimo mensaje -no
solo el ultimo-, porque una respuesta larga se parte: "ya lo tengo", cinco comandos,
y hasta el final la explicacion. Leyendo solo el ultimo bloque te quedabas con la
mitad, y casi siempre con la mitad que no dice nada.

Solo habla si el micro esta encendido: si apagaste la voz con M5, tampoco quieres
que te conteste hablando.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from voz.agentes import sesion  # noqa: E402
from voz.claude_code import leido  # noqa: E402
from voz.control import config, estado  # noqa: E402
from voz.habla import piper_voz, texto_hablable  # noqa: E402

HABLANDO_EL = ("grabando",)
ESPERA_TURNO = 45.0  # tope para no quedarse mudo si el micro se queda abierto

ESPERA_MAX = 4.0   # segundos que se le dan al transcript para acabar de escribirse
PAUSA = 0.25


def _registros(transcript):
    salida = []
    try:
        lineas = Path(transcript).read_text().splitlines()
    except OSError:
        return salida
    for linea in lineas:
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return salida


def _es_tu_mensaje(registro):
    """Tu turno de verdad, no el resultado de una herramienta (que tambien va como user)."""
    if registro.get("type") != "user":
        return False
    contenido = registro.get("message", {}).get("content", [])
    if isinstance(contenido, str):
        return True
    return not any(c.get("type") == "tool_result" for c in contenido)


def _texto(registro):
    contenido = registro.get("message", {}).get("content", [])
    if isinstance(contenido, str):
        return contenido.strip()
    trozos = [c.get("text", "") for c in contenido if c.get("type") == "text"]
    return "\n".join(t for t in trozos if t.strip()).strip()


def pendiente(transcript):
    """Lo que dijo el asistente y todavia no te ha leido, en orden. (texto, hasta_linea)

    No se corta por "tu ultimo mensaje": si hablas a media respuesta, tu frase queda
    EN MEDIO del turno y ese corte se comeria todo lo anterior. Se lleva una marca de
    hasta donde se leyo, asi nunca repite ni se salta un bloque.
    """
    registros = _registros(transcript)
    desde = leido.hasta(transcript)
    if desde is None:
        # Primera vez en esta conversacion: se arranca en tu ultimo mensaje, para no
        # soltarte de golpe toda la sesion en voz alta.
        desde = max((i for i, r in enumerate(registros) if _es_tu_mensaje(r)), default=0)
    dichos = []
    for registro in registros[desde:]:
        if registro.get("type") != "assistant" or registro.get("isSidechain"):
            continue
        texto = _texto(registro)
        if texto:
            dichos.append(texto)
    return "\n\n".join(dichos), len(registros)


def espera_a_que_cuaje(transcript):
    """Espera a que el ultimo bloque acabe de aterrizar en el archivo.

    El hook arranca antes de que Claude Code termine de escribir el cierre del turno,
    asi que mirar una sola vez te deja leyendo la respuesta de hace dos bloques. Se
    relee hasta que el texto deja de crecer. Va SIN candado -son segundos de espera-
    y la foto buena se toma despues, ya dentro del candado.
    """
    mejor = pendiente(transcript)[0]
    limite = time.monotonic() + ESPERA_MAX
    while time.monotonic() < limite:
        time.sleep(PAUSA)
        ahora = pendiente(transcript)[0]
        if len(ahora) <= len(mejor):
            return
        mejor = ahora


RECADO_MAX = 2400   # caracteres de la respuesta del agente que se le pasan al maestro


def pasa_al_maestro(ventana, texto):
    """Un agente que no es el maestro no habla: le cuenta al maestro y ese resume.

    Dos agentes leyendo su respuesta entera en voz alta se encimarian y no habria
    forma de saber cual es cual. Asi solo habla una voz -la de siempre- y ademas
    llega masticado: el maestro ya sabe en que andaba cada quien.

    El recado va en UNA linea a proposito: se entrega con `send-keys -l`, y ahi un
    salto de linea es un Enter, o sea el mensaje mandado a la mitad.
    """
    from voz.agentes import envio
    recorte = texto.strip()[:RECADO_MAX]
    if len(texto.strip()) > RECADO_MAX:
        recorte += "…"
    plano = " ".join(recorte.split())
    recado = (f"[aviso automático] El agente «{ventana}» acabó su turno. Lo último que "
              f"dijo fue: {plano} — Resúmeselo a Luis en voz alta en dos renglones: qué "
              f"hizo y si quedó bien o falta algo.")
    if envio.envia(recado):
        _traza(f"recado de {ventana} entregado al maestro")
        return True
    _traza(f"el maestro no pudo recibir el recado de {ventana}")
    return False


def avisa_que_acabo(ventana):
    """Plan B cuando el maestro no puede recibir el recado: el aviso pelon, hablado."""
    limite = time.monotonic() + ESPERA_TURNO
    while config.HABLANDO.exists() and time.monotonic() < limite:
        time.sleep(0.2)   # que acabe el que este hablando; no hay cola, se encimarian
    if piper_voz.di(f"{ventana} ya acabó", limpiar=False):
        _traza(f"aviso de que {ventana} acabo")
    else:
        _traza(f"no se pudo avisar que {ventana} acabo")


def _traza(motivo):
    """Sin esto el hook es una caja negra: Claude Code se traga su salida con
    2>/dev/null, asi que cuando no habla no hay forma de saber si ni siquiera corrio."""
    estado.apunta(f"{time.strftime('%H:%M:%S')}  TTS: {motivo}")


def main():
    # El turno acabo: se apaga aqui pase lo que pase, incluso si no toca hablar.
    config.TRABAJANDO.unlink(missing_ok=True)
    if not estado.escuchando():
        _traza("callado, el micro esta apagado")
        return 0
    ventana = sesion.ventana_actual()
    if not ventana:
        return 0
    try:
        evento = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _traza("no llego evento valido por stdin")
        return 0
    if evento.get("stop_hook_active"):
        _traza("callado, el turno lo encadeno otro hook")
        return 0

    transcript = evento.get("transcript_path", "")
    espera_a_que_cuaje(transcript)

    # Mirar y apuntar, de un tiron y con el candado agarrado. Es lo UNICO que impide
    # que este hook y el de avance se lleven el mismo bloque y se lo lean dos veces.
    # Se apunta antes de hablar a proposito: si te cansas y lo cortas, no te lo repite.
    with leido.turno():
        texto, hasta = pendiente(transcript)
        if texto:
            leido.apunta(transcript, hasta)

    # Los demas agentes no hablan: le pasan el recado al maestro y el resume.
    if ventana != sesion.MAESTRO:
        if not (texto and pasa_al_maestro(ventana, texto)):
            avisa_que_acabo(ventana)
        return 0

    if not texto:
        _traza("sin texto nuevo que leer")
        estado.calla_dialogo()
        return 0

    # Nunca arrancar a leer mientras tiene la tecla apretada, ni encima de un "ahí
    # voy" que siga sonando: no hay cola, las dos voces saldrian juntas.
    limite = time.monotonic() + ESPERA_TURNO
    while time.monotonic() < limite:
        if estado.pulso().get("fase") in HABLANDO_EL or config.HABLANDO.exists():
            time.sleep(0.2)
            continue
        break

    # La isla la muestra mientras piper la lee, para poder seguirla con la vista
    # aunque el audio vaya a la mitad.
    hablado = texto_hablable.limpia(texto)
    estado.dice("responde", hablado, vida=max(12.0, len(hablado) / 12))
    if piper_voz.di(texto):
        _traza(f"leido ({len(hablado)} caracteres, {texto.count(chr(10) * 2) + 1} bloques)")
    else:
        _traza("piper no pudo hablar (revisa .venv/bin/piper y la voz .onnx)")
    # En cuanto deja de sonar, fuera el punto: quedandose morado parecia ocupado y
    # no se sabia que ya se le podia hablar.
    estado.calla_dialogo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
