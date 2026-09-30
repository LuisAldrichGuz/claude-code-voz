"""Las averias conocidas del asistente: como se reconoce cada una y como se arregla.

Todas salieron de `docs/cuando-falla.md`, que hasta ahora habia que leer y aplicar a
mano. Cada revision es `(nombre, mira, repara)`:

  mira(ctx)   -> None si esta bien, o el texto de que esta mal
  repara(ctx) -> lo que hizo, o None si eso no se arregla solo

El orden importa: primero lo que sostiene a lo demas (demonio, microfono) y al final
lo que solo se puede avisar (teclas, hooks).
"""
import os
import subprocess
import time
from pathlib import Path

from voz.control import config
from voz.escucha import microfono


def _corre(*orden, espera=20):
    try:
        return subprocess.run(orden, capture_output=True, text=True, timeout=espera)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(orden, 1, "", "")


def _vive(patron, exacto=True):
    """PID del proceso, o None. Exacto compara el nombre; si no, la linea de orden."""
    salida = _corre("pgrep", "-x" if exacto else "-f", patron, espera=5).stdout.split()
    return int(salida[0]) if salida else None


def _lleva_vivo(pid):
    """Segundos que lleva corriendo ese proceso. -1 si ya no esta."""
    salida = _corre("ps", "-o", "etimes=", "-p", str(pid), espera=5).stdout.strip()
    return int(salida) if salida.isdigit() else -1


# --- el demonio --------------------------------------------------------------
# Solo se revisa desde fuera: corriendo DENTRO del demonio, reiniciarlo seria pedirle
# que se mate a si mismo a media revision.

def mira_demonio(ctx):
    if ctx.dentro:
        return None
    try:
        os.kill(int(config.PID.read_text()), 0)
        return None
    except (OSError, ValueError):
        return "no esta corriendo"


def repara_demonio(ctx):
    _corre("systemctl", "--user", "restart", "voz")
    for _ in range(20):
        time.sleep(0.5)
        if mira_demonio(ctx) is None:
            return "demonio reiniciado"
    return None


# --- la isla en pantalla -----------------------------------------------------

def mira_indicador(ctx):
    activo = _corre("systemctl", "--user", "is-active", "voz-indicador").stdout.strip()
    return None if activo == "active" else f"la isla esta {activo}"


def repara_indicador(ctx):
    _corre("systemctl", "--user", "restart", "voz-indicador")
    return "isla reiniciada"


# --- el microfono ------------------------------------------------------------
# Lo mas comun de todo: viene muteado de fabrica y, si alguien lo silencia, el
# asistente aparenta funcionar -oye, no entiende nada y nunca contesta-.

def mira_microfono(ctx):
    fuente = microfono.fuente_real()
    if fuente == "@DEFAULT_SOURCE@":
        return "no hay ninguna entrada de verdad, solo monitores de la salida"
    if _corre("pactl", "get-source-mute", fuente).stdout.strip().endswith("yes"):
        return f"{fuente} esta muteado"
    volumen = _corre("pactl", "get-source-volume", fuente).stdout
    bajo = [int(t.rstrip("%")) for t in volumen.split() if t.endswith("%")]
    if bajo and max(bajo) < 30:
        return f"{fuente} al {max(bajo)}% de volumen"
    return None


def repara_microfono(ctx):
    if microfono.fuente_real() == "@DEFAULT_SOURCE@":
        return None      # no hay tarjeta que abrir; eso no lo arregla un script
    microfono.destapa()
    return "microfono destapado y al 100%"


# --- whisper -----------------------------------------------------------------

def mira_instalacion(ctx):
    faltan = [str(p) for p in (config.WHISPER_SERVER, config.MODELO, config.PIPER,
                               config.VOZ_MODELO, config.MODELO_VAD) if not Path(p).exists()]
    return "falta " + ", ".join(faltan) if faltan else None


def mira_whisper(ctx):
    """Apagado no se revisa: con el micro cerrado, whisper DEBE estar dormido.

    Lo que se busca aqui es el servidor pegado: acepta la conexion -asi que el
    asistente lo da por bueno- pero no contesta una sola transcripcion. Pasa cuando
    se apaga y se vuelve a encender encima de un servidor que quedo huerfano.
    """
    if not config.ESCUCHANDO.exists():
        return None
    if not ctx.transcriptor.vivo():
        return "el servidor no responde en el puerto"
    if not ctx.transcriptor.responde():
        return "el puerto abre pero no transcribe: el servidor esta pegado"
    return None


def repara_whisper(ctx):
    """Se mata TODO whisper-server, no solo el del demonio.

    El que estorba suele ser justo el que ya no tiene dueno: sobrevivio a un
    `systemctl restart voz` y se quedo ocupando el puerto.
    """
    ctx.transcriptor.detiene()
    # Por nombre exacto (-x), nunca por linea de orden (-f): con -f el patron se
    # encuentra a si mismo en la orden que lo lanza y se para el proceso de al lado.
    # Y CONT antes de nada: uno detenido no atiende el TERM y sobrevive a todo.
    _corre("pkill", "-CONT", "-x", "whisper-server", espera=5)
    _corre("pkill", "-x", "whisper-server", espera=5)
    for _ in range(10):
        if not ctx.transcriptor.vivo():
            break
        time.sleep(0.3)
    if ctx.transcriptor.vivo():
        _corre("pkill", "-KILL", "-x", "whisper-server", espera=5)
        time.sleep(1.0)
    return "whisper levantado de nuevo" if ctx.transcriptor.arranca(espera=90) else None


# --- marcas pegadas ----------------------------------------------------------
# La isla se queda encendida porque un archivo de estado quedo tirado: el hook que lo
# apaga no corrio (interrumpiste con Escape) o el proceso se fue a medias.

RANCIO_HABLANDO = 120.0


def _rancia(marca, vida):
    try:
        return time.time() - marca.stat().st_mtime > vida
    except OSError:
        return False


def mira_marcas(ctx):
    pegadas = []
    if _rancia(config.HABLANDO, RANCIO_HABLANDO) and not _vive("piper"):
        pegadas.append("hablando")
    if _rancia(config.TRABAJANDO, config.TURNO_MAX):
        pegadas.append("trabajando")
    return "marca pegada: " + ", ".join(pegadas) if pegadas else None


def repara_marcas(ctx):
    for marca in (config.HABLANDO, config.TRABAJANDO):
        if _rancia(marca, 0):
            marca.unlink(missing_ok=True)
    config.DIALOGO.unlink(missing_ok=True)
    return "marcas viejas borradas"


# --- el Claude maestro -------------------------------------------------------

def _panel_muerto(sesion):
    """Se le pregunta a tmux, NO se lee la pantalla.

    Buscando "Pane is dead" en el texto, al maestro le basta con imprimir esa frase
    -revisando esto mismo, por ejemplo- para que lo den por muerto y lo reinicien a
    media faena.
    """
    banderas = _corre("tmux", "list-panes", "-t", f"{sesion.SESION}:{sesion.MAESTRO}",
                      "-F", "#{pane_dead}").stdout.split()
    return banderas[:1] == ["1"]


def mira_maestro(ctx):
    """Sin sesion no hay falla: nace sola al primer dictado, a proposito."""
    from voz.agentes import sesion
    if not sesion.existe():
        return None
    if _panel_muerto(sesion):
        return "el maestro se murio y dejo la ventana muerta"
    if sesion.pide_confianza():
        return "el maestro esta atorado pidiendo aprobar la carpeta"
    return None


def repara_maestro(ctx):
    """Se revive SOLO la ventana del maestro; los demas agentes ni se enteran."""
    from voz.agentes import sesion
    if not _panel_muerto(sesion):
        return None      # aprobar la carpeta lo decide el usuario, no un script
    ventana = f"{sesion.SESION}:{sesion.MAESTRO}"
    if _corre("tmux", "respawn-pane", "-k", "-c", sesion.CASA, "-t", ventana).returncode:
        return None
    time.sleep(0.5)
    _corre("tmux", "send-keys", "-t", ventana, "-l", "claude")
    _corre("tmux", "send-keys", "-t", ventana, "Enter")
    return "maestro revivido" if sesion.espera_listo() else None


# --- danos colaterales de reiniciar PipeWire ---------------------------------
# swayosd no se cae: se queda VIVO pero desconectado, y por eso despista tanto. Se
# reconoce por la edad: si lleva mas tiempo vivo que PipeWire, PipeWire renacio sin el.

DESFASE = 15


def mira_audio_sistema(ctx):
    rotos = []
    osd, pw = _vive("swayosd-server"), _vive("pipewire")
    if osd and pw and _lleva_vivo(osd) - _lleva_vivo(pw) > DESFASE:
        rotos.append("swayosd quedo desconectado de PipeWire")
    if not _vive("easyeffects"):
        rotos.append("EasyEffects no esta corriendo")
    return "; ".join(rotos) if rotos else None


def repara_audio_sistema(ctx):
    hecho = []
    osd, pw = _vive("swayosd-server"), _vive("pipewire")
    if osd and pw and _lleva_vivo(osd) - _lleva_vivo(pw) > DESFASE:
        _corre("omarchy-restart-swayosd")
        hecho.append("swayosd reconectado")
    if not _vive("easyeffects"):
        subprocess.Popen(["easyeffects", "--gapplication-service"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        hecho.append("EasyEffects levantado")
    return ", ".join(hecho) if hecho else None


# --- lo que solo se puede avisar ---------------------------------------------

def mira_teclas(ctx):
    binds = Path.home() / ".config" / "hypr" / "bindings.conf"
    try:
        texto = binds.read_text()
    except OSError:
        return "no se pudo leer bindings.conf"
    falta = [q for q in ("voz-tecla habla", "voz-tecla calla", "voz toggle")
             if q not in texto]
    return "faltan binds de la M5: " + ", ".join(falta) if falta else None


def mira_hooks(ctx):
    ajustes = Path.home() / ".claude" / "settings.json"
    try:
        texto = ajustes.read_text()
    except OSError:
        return "no se pudo leer ~/.claude/settings.json"
    if "lee_respuesta" not in texto:
        return "falta el hook que lee las respuestas en voz alta"
    if "marca_turno" not in texto:
        return "falta el hook que marca el turno del agente"
    return None


REVISIONES = (
    ("demonio",    mira_demonio,       repara_demonio),
    ("isla",       mira_indicador,     repara_indicador),
    ("microfono",  mira_microfono,     repara_microfono),
    ("instalado",  mira_instalacion,   None),
    ("whisper",    mira_whisper,       repara_whisper),
    ("marcas",     mira_marcas,        repara_marcas),
    ("maestro",    mira_maestro,       repara_maestro),
    ("audio",      mira_audio_sistema, repara_audio_sistema),
    ("teclas",     mira_teclas,        None),
    ("hooks",      mira_hooks,         None),
)
