"""El demonio: graba mientras tienes la tecla apretada y manda lo que dijiste.

Es "aprieta para hablar", no un micrófono siempre abierto. La version anterior escuchaba
todo el tiempo y tenia que adivinar si le hablabas tu o la tele: palabra de activacion
comparada por parecido, ventanas de sesion, respiros, rescates. Cada arreglo destapaba
otro y en un cuarto con un juego puesto seguia colandose. Apretar una tecla no se
adivina, asi que todo eso sobra.

Tres hilos:
  corre    espera las senales de la tecla
  graba    lee el microfono mientras la tecla este apretada (nada lento aqui dentro)
  trabaja  transcribe y entrega; puede tardar lo que quiera
"""
import queue
import signal
import threading
import time

from collections import deque

from voz.agentes import envio, sesion
from voz.control import config, estado
from voz.dictado import teclado
from voz.escucha.microfono import Microfono, destapa
from voz.transcripcion.whisper_local import Transcriptor


class Asistente:
    def __init__(self):
        self.transcriptor = Transcriptor()
        self.pendientes = queue.Queue()
        self.grabando = threading.Event()
        self.audio = bytearray()
        self.candado = threading.Lock()
        self.ultimo_texto = ""
        self.ultimo_uso = time.time()
        self.apretada_desde = 0.0
        self.trabajando = False
        self.vivo = True

    # --- la tecla ---------------------------------------------------------
    def aprietas(self):
        """Empieza a grabar. Si el asistente esta apagado, la tecla no hace nada.

        """
        if not estado.escuchando() or self.grabando.is_set():
            return
        self.apretada_desde = time.time()
        if not self.transcriptor.arranca():
            estado.avisa("Voz: no arrancó whisper", "Revisa voz-whisper/build", "critical")
            return
        with self.candado:
            self.audio = bytearray()
        self.ultimo_texto = ""
        self.grabando.set()
        estado.tono("despierto")

    def sueltas(self):
        """Al soltar la tecla: cierra y manda.

        Hubo tambien un modo "un toque abre, otro cierra" para no estar pegado al
        teclado. Se quito: con los dos modos en la misma tecla no habia forma de saber
        en cual estabas, y el dictado se quedaba abierto grabando el cuarto sin que se
        notara. Una tecla, un comportamiento.
        """
        self.cierra()

    def cierra(self):
        """Corta la grabacion y la manda a transcribir."""
        if not self.grabando.is_set():
            return
        self.grabando.clear()
        estado.tono("listo")
        with self.candado:
            audio, self.audio = bytes(self.audio), bytearray()
        self.ultimo_uso = time.time()
        if len(audio) < config.TASA * 2 * config.MINIMO:
            estado.apunta(f"{time.strftime('%H:%M:%S')}  soltaste demasiado rapido")
            return
        if _fuerza(audio) < config.MUDO:
            # Con audio mudo whisper no devuelve vacio: se inventa un "Gracias." o un
            # "Subtitulos por la comunidad", y eso acabaria en el chat como una orden.
            estado.apunta(f"{time.strftime('%H:%M:%S')}  [{len(audio) / (config.TASA * 2):4.1f}s] "
                          "no se oyo nada, no se mando")
            return
        self.trabajando = True
        self.pendientes.put(audio)

    def alterna(self):
        """Enciende o apaga el asistente entero (para juntas, o para soltar la VRAM)."""
        encendido = not estado.escuchando()
        estado.marca_escuchando(encendido)
        if encendido:
            destapa()
        else:
            self.grabando.clear()
            self.transcriptor.detiene()
        estado.tono("listo" if encendido else "dormido")
        estado.osd(encendido)
        self.late(fase="esperando" if encendido else "apagado")

    # --- ciclo de vida ----------------------------------------------------
    def instala_senales(self):
        signal.signal(signal.SIGUSR1, lambda *_: self.aprietas())
        signal.signal(signal.SIGUSR2, lambda *_: self.sueltas())
        signal.signal(signal.SIGHUP, lambda *_: self.alterna())
        signal.signal(signal.SIGTERM, lambda *_: self.apaga())
        signal.signal(signal.SIGINT, lambda *_: self.apaga())

    def apaga(self):
        self.vivo = False
        self.grabando.clear()
        self.transcriptor.detiene()

    def corre(self):
        import os
        self.instala_senales()
        estado.prepara_sonidos()
        config.RUN.mkdir(parents=True, exist_ok=True)
        config.PID.write_text(str(os.getpid()))
        estado.marca_escuchando(True)
        destapa()
        for tarea in (self.graba, self.trabaja, self.vigila):
            threading.Thread(target=tarea, daemon=True).start()
        while self.vivo:
            time.sleep(0.2)
        config.PID.unlink(missing_ok=True)

    # --- hilo GRABAR: rapido siempre --------------------------------------
    def graba(self):
        """Mantiene el microfono abierto mientras el asistente este encendido, pero
        solo GUARDA lo que entra con la tecla apretada; lo demas se tira frame a frame.

        Abrirlo justo al apretar se probo primero y `parec` tardaba metro y medio de
        segundo en arrancar: la frase empezaba cortada. Queda un colchon de COLCHON
        segundos hacia atras, para cuando aprietas un pelo tarde. Apagando el asistente
        (SUPER+ALT+M5) el microfono se cierra de verdad, que es lo que importa en una
        junta: ahi no hay que confiar en que el programa decida bien.
        """
        colchon = deque(maxlen=int(config.COLCHON * config.TASA / config.MUESTRAS_FRAME) + 1)
        while self.vivo:
            if not estado.escuchando():
                colchon.clear()
                time.sleep(0.3)
                continue
            with Microfono() as micro:
                for frame in micro.frames():
                    if not self.vivo or not estado.escuchando():
                        break
                    if not self.grabando.is_set():
                        colchon.append(frame)
                        continue
                    with self.candado:
                        if colchon:
                            self.audio = bytearray(b"".join(colchon)) + self.audio
                            colchon.clear()
                        self.audio += frame
                    self.late(fase="grabando", nivel=_fuerza(frame))

    # --- hilo TRABAJAR: aqui si se puede tardar ---------------------------
    def trabaja(self):
        while self.vivo:
            try:
                audio = self.pendientes.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.atiende(audio)
            finally:
                self.trabajando = not self.pendientes.empty()

    def atiende(self, audio):
        texto = self.transcriptor.texto_de(audio).strip()
        segundos = len(audio) / (config.TASA * 2)
        estado.apunta(f"{time.strftime('%H:%M:%S')}  [{segundos:4.1f}s] oido: {texto!r}")
        if not texto:
            return
        self.ultimo_texto = texto
        primera = texto.lower().split()[:1]
        if primera and primera[0].strip(",.") in ("escribe", "dicta", "teclea"):
            resto = texto.split(None, 1)[1] if " " in texto else ""
            estado.apunta(f"{time.strftime('%H:%M:%S')}  TECLEADO: {resto!r}")
            if resto and teclado.escribe(resto):
                teclado.enter()
            return
        entregado = envio.envia(texto)
        estado.apunta(f"{time.strftime('%H:%M:%S')}  "
                      f"{'AL AGENTE' if entregado else 'NO SE ENTREGÓ'}: {texto!r}")
        if entregado:
            # Decir la verdad: si el agente trae cola, tu orden espera turno.
            estado.dice("encolado" if sesion.encolado() else "trabajando", vida=600)
        else:
            self.ultimo_texto = ("aprueba la carpeta: voz ver"
                                 if sesion.pide_confianza() else "el agente no está listo")

    # --- hilo VIGILAR: la pantalla y la VRAM ------------------------------
    def vigila(self):
        while self.vivo:
            time.sleep(2.0)
            # Si interrumpes al agente con Escape, el hook que apaga el aviso nunca
            # corre. La pantalla del agente es la unica verdad.
            if estado.dialogo() and sesion.listo():
                estado.calla_dialogo()
            if (self.grabando.is_set()
                    and time.time() - self.apretada_desde > config.GRABACION_MAX):
                estado.apunta(f"{time.strftime('%H:%M:%S')}  dictado cerrado por el tope")
                self.cierra()
            # whisper ocupa ~2 GB de VRAM: sin usarse, que los suelte.
            if (self.transcriptor.vivo() and not self.grabando.is_set()
                    and time.time() - self.ultimo_uso > config.VRAM_LIBRE_TRAS):
                self.transcriptor.detiene()
                estado.apunta(f"{time.strftime('%H:%M:%S')}  whisper dormido, VRAM libre")
            if not self.grabando.is_set():
                self.late()

    # --- lo que pinta la isla ---------------------------------------------
    def late(self, fase=None, nivel=0.0):
        if fase is None:
            if self.trabajando:
                fase = "pensando"
            elif config.HABLANDO.exists():
                fase = "hablando"
            else:
                fase = "esperando" if estado.escuchando() else "apagado"
        estado.publica(fase=fase, nivel=nivel, texto=self.ultimo_texto)


def _fuerza(frame):
    """Cuanto se movio el ultimo frame, de 0 a 1. Solo para que la isla respire."""
    if not frame:
        return 0.0
    picos = max(abs(int.from_bytes(frame[i:i + 2], "little", signed=True))
                for i in range(0, len(frame) - 1, 2))
    return min(1.0, picos / 12000)


def main():
    Asistente().corre()
