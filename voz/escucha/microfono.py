"""Abre el microfono por PipeWire y entrega frames de 30 ms en PCM 16 kHz mono."""
import subprocess

SIN_ECO = "voz_sin_eco"


def fuente_real():
    """Nombre de una fuente de entrada DE VERDAD, nunca un monitor.

    `@DEFAULT_SOURCE@` no sirve: en esta maquina el default se va solo al
    `.monitor` de la salida, y entonces se graba lo que suena por las bocinas en
    vez del microfono. Eso es peor que no oir, porque aparenta funcionar.
    Se prefiere la tarjeta ALSA directa; EasyEffects queda de ultimo porque su
    cadena a veces se queda sin salida.
    """
    listado = subprocess.run(
        ["pactl", "list", "short", "sources"], capture_output=True, text=True
    ).stdout.splitlines()
    nombres = [l.split("\t")[1] for l in listado if len(l.split("\t")) > 1]
    entradas = [n for n in nombres if not n.endswith(".monitor")]
    # Si alguien vuelve a montar la cancelacion de eco de PipeWire, se prefiere; se
    # quito porque metia a EasyEffects en un bucle y dejaba la tarjeta sin salida, y
    # con la tecla ya no hace falta: el microfono solo guarda cuando la aprietas.
    if SIN_ECO in entradas:
        return SIN_ECO
    for n in entradas:
        if n.startswith("alsa_input"):
            return n
    return entradas[0] if entradas else "@DEFAULT_SOURCE@"


def destapa():
    """Quita el mute de la fuente por defecto.

    Sin esto el micro entrega silencio perfecto y el asistente parece descompuesto:
    oye, transcribe nada y nunca responde. Se llama al encender con M5, porque
    encender el asistente ES pedir que te oiga.
    """
    fuente = fuente_real()
    subprocess.run(["pactl", "set-source-mute", fuente, "0"], capture_output=True)
    subprocess.run(["pactl", "set-source-volume", fuente, "100%"], capture_output=True)

from voz.control import config


class Microfono:
    """Envoltura de `parec`. Se usa como contexto: `with Microfono() as m:`."""

    def __init__(self, fuente=None):
        self.fuente = fuente or fuente_real()
        self.proceso = None

    def __enter__(self):
        self.proceso = subprocess.Popen(
            [
                "parec",
                "--device", self.fuente,
                "--format=s16le",
                f"--rate={config.TASA}",
                "--channels=1",
                "--latency-msec=30",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return self

    def __exit__(self, *_):
        self.cerrar()
        return False

    def frames(self):
        """Itera frames crudos de MUESTRAS_FRAME muestras (2 bytes cada una)."""
        tamano = config.MUESTRAS_FRAME * 2
        while self.proceso and self.proceso.poll() is None:
            frame = self.proceso.stdout.read(tamano)
            if len(frame) < tamano:
                break
            yield frame

    def cerrar(self):
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
        self.proceso = None
