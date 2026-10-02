"""Hasta donde se leyo cada conversacion. Lo comparten los DOS hooks que hablan.

Hay dos que leen en voz alta -`lee_avance.py` en PostToolUse y `lee_respuesta.py`
en Stop- y los dos sacan el texto del mismo transcript. Lo unico que impide que
digan el mismo bloque es esta marca, asi que mirarla y actualizarla tiene que ser
UN solo paso indivisible y el mismo candado para los dos. Cuando cada hook tenia
el suyo -o ninguno- pasaba lo evidente: los dos leian el bloque 5, los dos lo
daban por dicho, y a Luis se lo contaban dos veces.

El archivo se puede mover con VOZ_MARCA. Las pruebas TIENEN que hacerlo: escribir
-o peor, borrar- la marca de verdad le pierde a Luis por donde iba y el hook le
relee de corrido todo lo que ya le habia dicho.
"""
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

from voz.control import config

ARCHIVO = Path(os.environ.get("VOZ_MARCA", config.RUN / "leido.json"))
CANDADO = ARCHIVO.parent / f"{ARCHIVO.name}.lock"


@contextmanager
def turno():
    """El candado unico. Se tiene agarrado para mirar y apuntar, nunca para hablar:
    hablar tarda segundos y dejaria al otro hook esperando toda la frase."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    with open(CANDADO, "w") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(cerrojo, fcntl.LOCK_UN)


def _todas():
    try:
        return json.loads(ARCHIVO.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def hasta(transcript):
    """Por que linea iba esa conversacion. None si es la primera vez."""
    return _todas().get(transcript)


def apunta(transcript, linea):
    """Se escribe aparte y se renombra: nadie puede leer el archivo a medias."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    marcas = _todas()
    marcas[transcript] = linea
    provisional = ARCHIVO.with_name(f"{ARCHIVO.name}.nuevo")
    provisional.write_text(json.dumps(marcas))
    provisional.replace(ARCHIVO)


def olvida(transcript):
    """Quita una conversacion de la marca. La usan las pruebas al limpiar."""
    marcas = _todas()
    if marcas.pop(transcript, None) is None:
        return False
    provisional = ARCHIVO.with_name(f"{ARCHIVO.name}.nuevo")
    provisional.write_text(json.dumps(marcas))
    provisional.replace(ARCHIVO)
    return True
