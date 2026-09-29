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
from voz.control import config, estado  # noqa: E402
from voz.habla import piper_voz, texto_hablable  # noqa: E402

HABLANDO_EL = ("grabando",)
ESPERA_TURNO = 45.0  # tope para no quedarse mudo si el micro se queda abierto

MARCA = config.RUN / "leido.json"
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


def _marca_leida():
    try:
        return json.loads(MARCA.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _apunta_leido(transcript, linea):
    config.RUN.mkdir(parents=True, exist_ok=True)
    marcas = _marca_leida()
    marcas[transcript] = linea
    MARCA.write_text(json.dumps(marcas))


def pendiente(transcript):
    """Lo que dijo el asistente y todavia no te ha leido, en orden. (texto, hasta_linea)

    No se corta por "tu ultimo mensaje": si hablas a media respuesta, tu frase queda
    EN MEDIO del turno y ese corte se comeria todo lo anterior. Se lleva una marca de
    hasta donde se leyo, asi nunca repite ni se salta un bloque.
    """
    registros = _registros(transcript)
    desde = _marca_leida().get(transcript)
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


def respuesta_completa(transcript):
    """Igual, pero esperando a que el ultimo bloque acabe de aterrizar en el archivo.

    El hook arranca antes de que Claude Code termine de escribir el cierre del turno,
    asi que preguntar una sola vez te deja leyendo la respuesta de hace dos bloques.
    Se relee hasta que el texto deja de crecer.
    """
    mejor, hasta = pendiente(transcript)
    limite = time.monotonic() + ESPERA_MAX
    while time.monotonic() < limite:
        time.sleep(PAUSA)
        ahora, tope = pendiente(transcript)
        if len(ahora) <= len(mejor):
            break
        mejor, hasta = ahora, tope
    return mejor, hasta


def es_el_maestro():
    """Solo habla el Claude que vive en la sesion tmux de voz.

    El hook esta puesto global, asi que sin esto CUALQUIER Claude Code abierto lee sus
    respuestas en voz alta: los que se manejan por teclado tambien, y acaban hablando
    todos encima. Se sube por los procesos padre hasta ver si alguno es el panel de
    tmux donde vive el maestro.
    """
    panes = subprocess.run(
        ["tmux", "list-panes", "-t", sesion.SESION, "-F", "#{pane_pid}"],
        capture_output=True, text=True)
    if panes.returncode != 0:
        return False
    duenos = {l.strip() for l in panes.stdout.splitlines() if l.strip()}
    pid = os.getpid()
    for _ in range(12):   # el arbol hook -> claude -> shell -> pane es cortito
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = f.read().rsplit(")", 1)[1].split()[1]
        except (OSError, IndexError):
            return False
        if pid in duenos:
            return True
        if pid == "1":
            return False
    return False


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
    if not es_el_maestro():
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
    texto, hasta = respuesta_completa(transcript)
    if not texto:
        _traza("sin texto nuevo que leer")
        estado.calla_dialogo()
        return 0

    # Nunca arrancar a leer mientras tiene la tecla apretada.
    limite = time.monotonic() + ESPERA_TURNO
    while estado.pulso().get("fase") in HABLANDO_EL and time.monotonic() < limite:
        time.sleep(0.2)

    # La isla la muestra mientras piper la lee, para poder seguirla con la vista
    # aunque el audio vaya a la mitad.
    hablado = texto_hablable.limpia(texto)
    estado.dice("responde", hablado, vida=max(12.0, len(hablado) / 12))
    _apunta_leido(transcript, hasta)   # antes de hablar: si te cansas y lo cortas, no te lo repite
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
