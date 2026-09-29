"""La sesion tmux donde viven los Claude Code que manejas por voz.

Teclear en "la ventana enfocada" limita todo a una sola terminal y te obliga a
tenerla al frente. Aqui los agentes viven en una sesion tmux propia: les llega lo
que dictas aunque estes en el navegador, y el maestro puede abrir mas agentes el
mismo (una ventana tmux por cada uno).
"""
import json
import os
import subprocess
import time
from pathlib import Path

SESION = "voz"
MAESTRO = "maestro"
CASA = os.path.expanduser("~")

# Con esto en pantalla, Claude Code ya acepta lo que se le escriba.
LISTO = ("shift+tab", "for shortcuts", "auto mode on")
# Y con esto esta atorado pidiendo permiso para la carpeta.
CONFIANZA = "Is this a project you created"


def _tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def existe():
    return _tmux("has-session", "-t", SESION).returncode == 0


def pantalla(agente=None):
    """Lo que se ve ahora mismo en el agente."""
    return _tmux("capture-pane", "-p", "-t", destino(agente) or SESION).stdout


def asegura():
    """Deja lista la sesion con el Claude maestro. True si quedo servible."""
    if existe():
        return True

    # La ventana corre un SHELL, no `claude` directo: si Claude se cae o se sale,
    # la ventana sobrevive y se puede ver que paso. Lanzarlo como comando de la
    # sesion hacia que un tropiezo se llevara la sesion entera sin dejar rastro.
    creada = _tmux("new-session", "-d", "-s", SESION, "-n", MAESTRO, "-c", CASA,
                   "-x", "200", "-y", "50")
    if creada.returncode != 0:
        return False
    _tmux("set-option", "-t", SESION, "remain-on-exit", "on")
    time.sleep(0.5)
    _tmux("send-keys", "-t", f"{SESION}:{MAESTRO}", "-l", "claude")
    _tmux("send-keys", "-t", f"{SESION}:{MAESTRO}", "Enter")
    return espera_listo()


# Señales que Claude Code pinta cuando esta ocupado o con cola.
OCUPADO = ("esc to interrupt", "tokens)")
ENCOLADO = "queued message"


def ocupado(agente=None):
    """True si el agente esta trabajando en algo ahora mismo."""
    vista = pantalla(agente).lower()
    return any(p in vista for p in OCUPADO)


def encolado(agente=None):
    """True si tu orden quedo formada detras de otra.

    Importa mostrarlo: si no, parece que el asistente contesta lo del mensaje
    anterior, cuando en realidad el agente todavia no llega al tuyo.
    """
    return ENCOLADO in pantalla(agente).lower()


def listo(agente=None):
    """True si se le puede escribir: en su prompt y sin dialogos abiertos.

    Estar ocupado no lo descalifica -Claude Code encola lo que le llega-; lo que
    nunca debe recibir texto es un agente detenido en un dialogo, porque el Enter
    del dictado contestaria ESE dialogo.
    """
    vista = pantalla(agente)
    return any(p in vista for p in LISTO) and CONFIANZA not in vista


def pide_confianza(agente=None):
    """True si esta detenido esperando que apruebes la carpeta."""
    return CONFIANZA in pantalla(agente)


def espera_listo(agente=None, limite=60):
    """Aguanta a que Claude Code muestre su interfaz.

    Tarda varios segundos en abrir; si se le escribe antes, el texto cae en el
    vacio y parece que el dictado no sirve.
    """
    fin = time.time() + limite
    while time.time() < fin:
        vista = pantalla(agente)
        if any(p in vista for p in LISTO):
            time.sleep(0.3)  # que acabe de pintar antes de escribirle
            return True
        if CONFIANZA in vista:
            return False  # pide permiso de carpeta: eso lo decide el usuario
        time.sleep(0.5)
    return False


def agentes():
    """Nombres de los agentes vivos, en orden. El primero es el maestro."""
    if not existe():
        return []
    salida = _tmux("list-windows", "-t", SESION, "-F", "#{window_name}").stdout
    return [n for n in salida.splitlines() if n]


def destino(nombre=None):
    """Convierte un nombre hablado en un destino de tmux.

    Sin nombre, manda al maestro. Con nombre, busca el agente que empiece igual,
    para que "gotchi" encuentre a "gotchi-backend" sin deletrearlo.
    """
    vivos = agentes()
    if not vivos:
        return None
    if not nombre:
        return f"{SESION}:{vivos[0]}"
    pista = nombre.strip().lower()
    for n in vivos:
        if n.lower().startswith(pista):
            return f"{SESION}:{n}"
    return f"{SESION}:{vivos[0]}"


def pid_del_maestro():
    """PID del proceso `claude` que corre en la ventana del maestro."""
    panel = _tmux("list-panes", "-t", f"{SESION}:1", "-F", "#{pane_pid}")
    if panel.returncode != 0:
        return None
    raiz = panel.stdout.strip().splitlines()
    if not raiz:
        return None
    hijos = subprocess.run(["pgrep", "-P", raiz[0]], capture_output=True, text=True)
    for pid in hijos.stdout.split():
        orden = Path(f"/proc/{pid}/comm")
        try:
            if orden.read_text().strip() == "claude":
                return int(pid)
        except OSError:
            continue
    return None


def estado_oficial():
    """Lo que Claude Code dice de si mismo: 'busy', 'waiting', 'idle' o None.

    `claude agents --json` es la via documentada para preguntarle a Claude Code por sus
    sesiones. Sirve de red: las marcas de los hooks son instantaneas pero se pueden
    quedar pegadas -si lo interrumpes con Escape, el hook de fin no llega a correr-.
    """
    pid = pid_del_maestro()
    if not pid:
        return None
    salida = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True)
    if salida.returncode != 0:
        return None
    try:
        for agente in json.loads(salida.stdout):
            if agente.get("pid") == pid:
                return agente.get("status")
    except (json.JSONDecodeError, TypeError):
        return None
    return None
