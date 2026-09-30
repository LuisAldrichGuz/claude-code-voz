"""Habla con whisper-server (whisper.cpp + CUDA) para pasar audio a texto.

El servidor se arranca una vez y deja el modelo en la VRAM de la 5070: cada frase
tarda decimas en vez de recargar 1.6 GB. Al apagar el micro se mata y la GPU queda libre.
"""
import json
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from voz.control import config


def _wav(pcm):
    """Envuelve el PCM crudo en una cabecera WAV de 16 kHz mono."""
    cabecera = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1,
        config.TASA, config.TASA * 2, 2, 16, b"data", len(pcm),
    )
    return cabecera + pcm


class Transcriptor:
    def __init__(self):
        self.proceso = None
        self.url = f"http://127.0.0.1:{config.PUERTO}/inference"

    def vivo(self):
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", config.PUERTO)) == 0

    def arranca(self, espera=180):
        """Levanta el servidor y espera a que el modelo termine de subir a la GPU."""
        if self.vivo():
            return True
        # En una variable local, no solo en el atributo: apagando el asistente a media
        # carga, `detiene()` deja `self.proceso` en None desde otro hilo y el poll de
        # abajo reventaba el demonio entero.
        proceso = subprocess.Popen(
            [
                str(config.WHISPER_SERVER),
                "-m", str(config.MODELO),
                "-l", config.IDIOMA,
                "--port", str(config.PUERTO),
                "-t", "4",
                "--no-timestamps",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.proceso = proceso
        limite = time.time() + espera
        while time.time() < limite:
            if self.vivo():
                return True
            if proceso.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    def detiene(self):
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
        self.proceso = None

    def responde(self, espera=15):
        """Prueba de verdad: le manda dos decimas de silencio y espera contestacion.

        `vivo()` solo mira si el puerto acepta conexiones, y un servidor pegado la
        acepta igual -contesta el kernel, no whisper-. Asi es como un servidor huerfano
        que sobrevivio a un reinicio parece sano y se traga todas las frases.
        """
        try:
            self._pide(b"\x00" * (config.TASA // 5), espera)
            return True
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
            return False

    def texto_de(self, pcm, espera=60):
        """Audio crudo -> texto. Cadena vacia si no se entendio nada."""
        try:
            return self._pide(pcm, espera)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
            return ""

    def _pide(self, pcm, espera):
        """Manda el audio al servidor. Revienta si no contesta: eso lo usa `responde`."""
        frontera = uuid.uuid4().hex
        partes = []
        for campo, valor in (("temperature", "0.0"), ("response_format", "json"),
                             ("language", config.IDIOMA)):
            partes.append(
                f'--{frontera}\r\nContent-Disposition: form-data; name="{campo}"'
                f"\r\n\r\n{valor}\r\n".encode()
            )
        partes.append(
            f'--{frontera}\r\nContent-Disposition: form-data; name="file";'
            ' filename="voz.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
            + _wav(pcm) + b"\r\n"
        )
        partes.append(f"--{frontera}--\r\n".encode())

        peticion = urllib.request.Request(
            self.url,
            data=b"".join(partes),
            headers={"Content-Type": f"multipart/form-data; boundary={frontera}"},
        )
        with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
            return json.loads(respuesta.read()).get("text", "").strip()
