"""Entrega lo que dictaste al agente, sin quitarte el foco de donde estes."""
import subprocess
import time

from voz.agentes import sesion


def envia(texto, agente=None):
    """Escribe el texto en el agente y lo manda. False si no habia a quien.

    Va en dos golpes -texto y luego Enter- porque mandarlos juntos hace que la
    interfaz de Claude Code a veces se coma el salto de linea.
    """
    if not texto.strip():
        return False
    if not sesion.asegura():
        return False
    ruta = sesion.destino(agente)
    if not ruta:
        return False
    # Nunca escribirle a un agente que no esta en su prompt: si esta en un dialogo,
    # el Enter del dictado contesta ESE dialogo. Asi se murio el primer maestro:
    # el Enter cayo sobre "No, exit" y cerro Claude.
    if not sesion.listo(agente):
        return False

    escrito = subprocess.run(
        ["tmux", "send-keys", "-t", ruta, "-l", texto.strip()], capture_output=True
    )
    if escrito.returncode != 0:
        return False
    time.sleep(0.12)
    subprocess.run(["tmux", "send-keys", "-t", ruta, "Enter"], capture_output=True)
    return True


def ver(agente=None):
    """Abre una terminal enganchada a la sesion, para mirar lo que hace."""
    ruta = sesion.destino(agente) or sesion.SESION
    subprocess.Popen([
        "uwsm-app", "--", "xdg-terminal-exec", "--",
        "tmux", "attach", "-t", ruta,
    ])
