"""Escribe el texto dictado en la ventana que tengas enfocada, como si lo tecleara."""
import subprocess
import time

TECLEO = ["wtype", "-d", "2", "--"]


def escribe(texto):
    """Suelta el texto en la ventana enfocada. False si wtype no pudo."""
    if not texto:
        return False
    return subprocess.run(TECLEO + [texto], capture_output=True).returncode == 0


def enter():
    """Manda Return: en una terminal con Claude Code, esto envia el mensaje."""
    time.sleep(0.15)  # deja que el ultimo caracter aterrice antes de enviar
    subprocess.run(["wtype", "-k", "Return"], capture_output=True)


def borra_linea():
    """Ctrl+U: limpia lo dictado si te arrepentiste antes de enviar."""
    subprocess.run(["wtype", "-M", "ctrl", "u", "-m", "ctrl"], capture_output=True)
