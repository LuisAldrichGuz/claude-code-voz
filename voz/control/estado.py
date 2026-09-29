"""Lo que el sistema te muestra y te suena: marcas en disco, avisos y tonos."""
import json
import os
import threading
import math
import time
import struct
import subprocess
import wave

from voz.control import config

SONIDOS = config.RAIZ / "sonidos"
TONOS = {"despierto": (880, 0.12), "dormido": (440, 0.12), "listo": (660, 0.1)}


def prepara_sonidos():
    """Genera los tres tonos la primera vez. Son senos cortos, no hacen falta assets."""
    SONIDOS.mkdir(parents=True, exist_ok=True)
    for nombre, (hz, dur) in TONOS.items():
        destino = SONIDOS / f"{nombre}.wav"
        if destino.exists():
            continue
        tasa, muestras = 44100, []
        total = int(tasa * dur)
        for i in range(total):
            desvanece = min(1.0, (total - i) / (tasa * 0.03))  # cola suave, sin chasquido
            muestras.append(int(12000 * desvanece * math.sin(2 * math.pi * hz * i / tasa)))
        with wave.open(str(destino), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack(f"<{len(muestras)}h", *muestras))


def tono(nombre):
    archivo = SONIDOS / f"{nombre}.wav"
    if archivo.exists():
        subprocess.Popen(["paplay", str(archivo)], stderr=subprocess.DEVNULL)


def avisa(titulo, cuerpo="", urgencia="low", vida=2500):
    subprocess.run(
        ["notify-send", "-u", urgencia, "-t", str(vida), "-a", "voz", titulo, cuerpo],
        capture_output=True,
    )


def osd(encendido):
    """El mismo aviso en pantalla que usa la tecla de mutear el microfono.

    Vale la pena que sea el OSD del sistema y no la isla: apagar el asistente se hace
    justo cuando no se quiere que aparezca nada raro -en una reunion, por ejemplo- y
    ahi lo que se necesita es la confirmacion de siempre, en el lugar de siempre.
    """
    avisa_osd("Chat de voz activado" if encendido else "Chat de voz desactivado",
              "audio-input-microphone-symbolic" if encendido
              else "microphone-sensitivity-muted-symbolic")


def avisa_osd(mensaje, icono):
    """Aviso corto en el OSD del sistema, en el mismo lugar que el del volumen."""
    subprocess.Popen(
        ["omarchy-swayosd-client", "--custom-message", mensaje, "--custom-icon", icono],
        stderr=subprocess.DEVNULL)


def escuchando():
    return config.ESCUCHANDO.exists()


def marca_escuchando(activo):
    config.RUN.mkdir(parents=True, exist_ok=True)
    if activo:
        config.ESCUCHANDO.touch()
    else:
        config.ESCUCHANDO.unlink(missing_ok=True)


def apunta(linea):
    """Bitacora corta, para saber que oyo cuando algo salga raro."""
    config.REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    with open(config.REGISTRO, "a") as f:
        f.write(linea.rstrip() + "\n")


def publica(**datos):
    """Deja el pulso del demonio en disco para que el indicador lo pinte.

    Escritura atomica (archivo temporal + rename) porque el indicador lo lee 20
    veces por segundo y no debe toparse con medio JSON.
    """
    config.RUN.mkdir(parents=True, exist_ok=True)
    datos["hora"] = time.time()
    # Un temporal POR HILO. Con uno solo, dos hilos publicando a la vez se pisaban: el
    # primero renombraba y al segundo le estallaba un FileNotFoundError que se llevaba
    # el hilo del microfono entero, y el asistente se quedaba sordo sin decir nada.
    temporal = config.PULSO.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporal.write_text(json.dumps(datos))
        temporal.replace(config.PULSO)
    except OSError:
        temporal.unlink(missing_ok=True)


DORMIDO = {"fase": "apagado", "nivel": 0.0, "umbral": 1.0, "texto": ""}


def pulso():
    """Ultimo estado del microfono. Si esta rancio se ignora.

    Un pulso viejo significa que el demonio se atoro; darlo por bueno dejaria la
    isla clavada en "grabando" y taparia la respuesta del agente.
    """
    try:
        d = json.loads(config.PULSO.read_text())
    except (OSError, json.JSONDecodeError):
        return dict(DORMIDO)
    return d if time.time() - d.get("hora", 0) < 1.5 else dict(DORMIDO)


def dice(estado_agente, texto="", vida=20.0):
    """Anota que hace el agente: "trabajando" o "responde".

    Va en su propio archivo porque el pulso del microfono se reescribe 20 veces
    por segundo y se llevaria la respuesta por delante.
    """
    config.RUN.mkdir(parents=True, exist_ok=True)
    temporal = config.DIALOGO.with_suffix(".tmp")
    temporal.write_text(json.dumps({
        "estado": estado_agente, "texto": texto,
        "hasta": time.time() + vida,
    }))
    temporal.replace(config.DIALOGO)


def dialogo():
    """Lo ultimo que dijo o hizo el agente, si sigue vigente."""
    try:
        d = json.loads(config.DIALOGO.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return d if d.get("hasta", 0) > time.time() else None


def calla_dialogo():
    config.DIALOGO.unlink(missing_ok=True)
