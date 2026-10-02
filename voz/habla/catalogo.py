"""Que voces hay instaladas y cual esta puesta ahora.

La eleccion vive en un archivo, no en una variable de entorno: tiene que seguir
puesta cuando se reinicie la maquina y cuando la cambie el comando `voz motor`.
"""
from pathlib import Path

from voz.control import config

CARPETA = config.RAIZ / "voces"
ELECCION = config.CASA / ".local" / "state" / "voz-motor"
PREDETERMINADA = "es_ES-glados-medium"


def disponibles():
    """Los nombres de las voces que hay en voces/, sin la extension."""
    return sorted(p.stem for p in CARPETA.glob("*.onnx") if (p.parent / f"{p.name}.json").exists())


def actual():
    """La voz puesta. Si la elegida ya no esta, la que venga de fabrica."""
    try:
        elegida = ELECCION.read_text().strip()
    except OSError:
        elegida = PREDETERMINADA
    for nombre in (elegida, PREDETERMINADA, *disponibles()):
        modelo = CARPETA / f"{nombre}.onnx"
        if modelo.exists():
            return modelo
    return CARPETA / f"{PREDETERMINADA}.onnx"


def elige(nombre):
    """Deja puesta otra voz. Devuelve False si no esta instalada."""
    if nombre not in disponibles():
        return False
    ELECCION.parent.mkdir(parents=True, exist_ok=True)
    ELECCION.write_text(nombre)
    return True
