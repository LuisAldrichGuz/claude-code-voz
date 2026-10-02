"""Lee texto en voz alta con piper (voz neuronal en espanol, offline y en CPU)."""
import json
import subprocess

from voz.control import config
from voz.habla import catalogo, texto_hablable


def _tasa():
    """La tasa de muestreo la declara el propio modelo en su .json."""
    try:
        with open(f"{catalogo.actual()}.json") as f:
            return json.load(f)["audio"]["sample_rate"]
    except (OSError, KeyError, json.JSONDecodeError):
        return 22050


def disponible():
    return config.PIPER.exists() and catalogo.actual().exists()


def di(texto, limpiar=True):
    """Habla. Mientras suena deja la marca HABLANDO para que el micro se ignore a si mismo."""
    frase = texto_hablable.limpia(texto) if limpiar else texto
    if not frase or not disponible():
        return False

    # Nunca dos voces encima. El hook corre en segundo plano y por cada turno arranca
    # uno: con respuestas cortas seguidas, el siguiente empezaba mientras el anterior
    # seguia leyendo y se oian los dos a la vez. Gana siempre lo mas reciente.
    callate()
    config.RUN.mkdir(parents=True, exist_ok=True)
    config.HABLANDO.touch()
    try:
        piper = subprocess.Popen(
            # Sin banderas: el modelo lee como fue entrenado para leer.
            [str(config.PIPER), "-m", str(catalogo.actual()), "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        reproductor = subprocess.Popen(
            ["paplay", "--raw", "--format=s16le", f"--rate={_tasa()}", "--channels=1",
             f"--volume={int(65536 * config.VOZ_VOLUMEN)}"],
            stdin=piper.stdout, stderr=subprocess.DEVNULL,
        )
        piper.stdout.close()
        piper.communicate(frase.encode())
        reproductor.wait()
        return True
    finally:
        config.HABLANDO.unlink(missing_ok=True)


def callate():
    """Corta lo que se este leyendo ahora mismo."""
    subprocess.run(["pkill", "-f", "piper -m"], capture_output=True)
    config.HABLANDO.unlink(missing_ok=True)
