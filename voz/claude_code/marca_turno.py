#!/usr/bin/env python3
"""Hook `UserPromptSubmit`: deja dicho que el agente EMPEZO a trabajar.

Antes esto se adivinaba mirando la pantalla de tmux, y entre una herramienta y la
siguiente el prompt reaparece un instante: el punto se apagaba a media faena y parecia
que no habia hecho caso. Claude Code avisa cuando empieza un turno y cuando termina, asi
que no hay nada que adivinar: aqui se enciende la marca y el hook `Stop` la apaga.

Solo cuenta el Claude maestro, el que vive en la sesion tmux de voz.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from voz.claude_code.lee_respuesta import es_el_maestro  # noqa: E402
from voz.control import config  # noqa: E402


def main():
    if not es_el_maestro():
        return 0
    config.RUN.mkdir(parents=True, exist_ok=True)
    config.TRABAJANDO.touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
