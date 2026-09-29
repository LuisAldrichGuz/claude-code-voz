"""El demonio, como una maquina de estados: un paso a la vez, nunca dos encima.

Los estados son el camino completo de una conversacion, en orden y sin atajos:

    DORMIDO   gris     esperando el nombre; lo demas que suene no existe
    OYENDO    verde    te esta grabando
    RESPIRO   cian     te callaste: sigue siendo TU mensaje, puedes seguir
    PENSANDO  ambar    transcribiendo y el agente trabajando
    HABLANDO  morado   leyendo su respuesta
              -> vuelve a DORMIDO, y para hablarle hay que invocarlo otra vez

Solo se le puede hablar en DORMIDO y en OYENDO/RESPIRO. Mientras piensa o habla, el
microfono no entrega nada: es una conversacion uno a uno. Esto no es una manera elegante
de escribirlo, es el arreglo: antes eran seis banderas sueltas (grabando, borrador,
invocado_hasta, mi_turno_desde, sordo_hasta, trabajando) y se pisaban entre ellas, asi
que se mandaban mensajes dobles, el microfono se abria antes de tiempo y el punto de la
isla no decia lo que de verdad estaba pasando.

Tres hilos: `graba` lee el microfono y no hace nada lento; `trabaja` transcribe y
entrega; `vigila` cuida los tiempos y lo que pinta la isla.
"""
import queue
import signal
import threading
import time
from collections import deque

from voz.agentes import envio, sesion
from voz.control import config, estado
from voz.dictado import teclado
from voz.escucha import palabra_clave
from voz.escucha.deteccion_voz import CortadorDeVoz
from voz.escucha.microfono import Microfono, destapa
from voz.transcripcion.whisper_local import Transcriptor

APAGADO = "apagado"
DORMIDO = "esperando"
OYENDO = "grabando"
RESPIRO = "respiro"
PENSANDO = "pensando"
HABLANDO = "hablando"

# Estados en los que el microfono SI entrega lo que oye.
TE_OYE = (DORMIDO, OYENDO, RESPIRO)


class Asistente:
    def __init__(self):
        self.transcriptor = Transcriptor()
        self.cortador = CortadorDeVoz()
        self.pendientes = queue.Queue()
        self.candado = threading.Lock()

        self.estado = DORMIDO
        self.desde = time.time()      # cuando se entro al estado actual
        self.borrador = []            # lo que llevas dicho de este mensaje
        self.tecla = False            # la M5 esta apretada ahora mismo
        self.audio = bytearray()      # lo grabado con la tecla
        self.ultimo_texto = ""
        self.ultimo_uso = time.time()
        self.ultima_voz = 0.0    # ultima vez que se te oyo algo, para no cerrarte el turno
        self.ultima_consulta = 0.0
        self.turno_whisper = threading.Lock()
        self.vivo = True

    # --- el estado ---------------------------------------------------------
    def pasa_a(self, nuevo):
        """Unico sitio donde se cambia de estado, para que no haya dos a la vez."""
        with self.candado:
            if self.estado == nuevo:
                return
            self.estado = nuevo
            self.desde = time.time()
        self.late()

    @property
    def lleva(self):
        return time.time() - self.desde

    def te_oye(self):
        return self.estado in TE_OYE and estado.escuchando()

    # --- la tecla ----------------------------------------------------------
    def aprietas(self):
        """Mantener la M5 graba sin necesidad de decir el nombre."""
        if not estado.escuchando() or self.tecla or self.estado not in TE_OYE:
            return
        if not self.transcriptor.arranca():
            estado.avisa("Voz: no arrancó whisper", "Revisa voz-whisper/build", "critical")
            return
        with self.candado:
            self.audio = bytearray()
        self.tecla = True
        self.cortador.reinicia()
        estado.tono("despierto")
        self.pasa_a(OYENDO)

    def sueltas(self):
        if not self.tecla:
            return
        self.tecla = False
        estado.tono("listo")
        with self.candado:
            audio, self.audio = bytes(self.audio), bytearray()
        self.ultimo_uso = time.time()
        if len(audio) < config.TASA * 2 * config.MINIMO:
            estado.apunta(f"{time.strftime('%H:%M:%S')}  soltaste demasiado rapido")
            self.pasa_a(DORMIDO if not self.borrador else RESPIRO)
            return
        if _fuerza(audio) < config.MUDO:
            # Con audio mudo whisper no devuelve vacio: se inventa un "Gracias." y eso
            # acabaria en el chat como una orden.
            estado.apunta(f"{time.strftime('%H:%M:%S')}  no se oyo nada, no se mando")
            self.pasa_a(DORMIDO if not self.borrador else RESPIRO)
            return
        self.pendientes.put((audio, False))

    def alterna(self):
        """Enciende o apaga el asistente entero (para una junta, o soltar la VRAM)."""
        encendido = not estado.escuchando()
        estado.marca_escuchando(encendido)
        if encendido:
            destapa()
        else:
            self.tecla = False
            self.transcriptor.detiene()
        estado.tono("listo" if encendido else "dormido")
        estado.osd(encendido)
        self.pasa_a(DORMIDO if encendido else APAGADO)

    # --- ciclo de vida -----------------------------------------------------
    def instala_senales(self):
        signal.signal(signal.SIGUSR1, lambda *_: self.aprietas())
        signal.signal(signal.SIGUSR2, lambda *_: self.sueltas())
        signal.signal(signal.SIGHUP, lambda *_: self.alterna())
        signal.signal(signal.SIGTERM, lambda *_: self.apaga())
        signal.signal(signal.SIGINT, lambda *_: self.apaga())

    def apaga(self):
        self.vivo = False
        self.tecla = False
        self.transcriptor.detiene()

    def corre(self):
        import os
        self.instala_senales()
        estado.prepara_sonidos()
        config.RUN.mkdir(parents=True, exist_ok=True)
        config.PID.write_text(str(os.getpid()))
        estado.marca_escuchando(True)
        destapa()
        # Se levanta ya: esperando al primer uso, la primera frase se queda esperando a
        # que el modelo suba a la GPU.
        self.transcriptor.arranca()
        for tarea in (self.graba, self.trabaja, self.vigila, self.mira):
            threading.Thread(target=self._sin_morirse, args=(tarea,), daemon=True).start()
        while self.vivo:
            time.sleep(0.2)
        config.PID.unlink(missing_ok=True)

    def _sin_morirse(self, tarea):
        """Vuelve a levantar el hilo si se cae, y lo deja escrito.

        Un hilo de estos muriendo deja al asistente sordo o mudo sin ninguna senal: el
        demonio sigue "vivo", el microfono sigue "encendido" y no pasa nada.
        """
        while self.vivo:
            try:
                tarea()
                return
            except Exception as falla:
                estado.apunta(f"{time.strftime('%H:%M:%S')}  SE CAYO {tarea.__name__}: "
                              f"{falla!r}; lo levanto otra vez")
                time.sleep(1.0)

    # --- hilo GRABAR: rapido siempre ---------------------------------------
    def graba(self):
        """El microfono queda abierto, pero solo se GUARDA en los estados que te oyen.

        Abrirlo justo al necesitarlo se probo y `parec` tardaba metro y medio de segundo
        en arrancar: la frase empezaba cortada. Apagando el asistente se cierra de
        verdad, que es lo unico que vale en una junta.
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
                    if not self.te_oye():
                        # Ni se graba: es la unica forma de que no se cuele el cuarto
                        # entero mientras el agente contesta.
                        self.cortador.reinicia()
                        colchon.clear()
                        continue
                    if self.tecla:
                        with self.candado:
                            if colchon:
                                self.audio = bytearray(b"".join(colchon)) + self.audio
                                colchon.clear()
                            self.audio += frame
                        self.late(nivel=_fuerza(frame))
                        continue
                    colchon.append(frame)
                    self.sin_tecla(frame)

    def sin_tecla(self, frame):
        """Manos libres: el detector de voz corta la frase y se manda a transcribir."""
        frase = self.cortador.empuja(frame)
        if frase is not None:
            self.pendientes.put((frase, True))
            # Si el turno ya estaba abierto SIGUE abierto, aunque todavia no haya nada
            # guardado: diciendo solo el nombre y arrancando a hablar, al cerrar esa
            # primera frase el estado se caia a dormido y lo que seguia se tiraba por
            # no llevar el nombre.
            if self.estado in (OYENDO, RESPIRO):
                self.pasa_a(RESPIRO)
            else:
                self.pasa_a(DORMIDO)
        if self.cortador.grabando:
            self.ultima_voz = time.time()
        if frase is None and self.cortador.grabando and self.estado in (RESPIRO, OYENDO):
            # El verde solo DESPUES de que se te reconocio el nombre. Encenderlo con
            # cualquier voz que el detector oyera era mentir: con alguien hablando de
            # fondo parecia que te estaba atendiendo, y no le estaba haciendo caso a
            # nadie. Hasta que no se transcribe la frase no se sabe si eras tu.
            self.pasa_a(OYENDO)
            self.late(nivel=self.cortador.probabilidad)

    # --- hilo TRABAJAR: aqui si se puede tardar ----------------------------
    def trabaja(self):
        while self.vivo:
            try:
                audio, sin_tecla = self.pendientes.get(timeout=0.5)
            except queue.Empty:
                continue
            self.atiende(audio, sin_tecla)

    def atiende(self, audio, sin_tecla):
        # Aqui tambien, no solo al apretar la tecla: el vigilante apaga whisper para
        # soltar la VRAM, y lo que se oia sin tecla llegaba a un servidor caido y volvia
        # siempre vacio. Se oia perfecto y no pasaba absolutamente nada.
        if not self.transcriptor.arranca():
            estado.apunta(f"{time.strftime('%H:%M:%S')}  whisper no arranco, frase perdida")
            return
        self.ultimo_uso = time.time()
        with self.turno_whisper:
            texto = self.transcriptor.texto_de(audio).strip()
        segundos = len(audio) / (config.TASA * 2)
        estado.apunta(f"{time.strftime('%H:%M:%S')}  [{segundos:4.1f}s fuerza {_fuerza(audio):.2f}"
                      f"{' sin tecla' if sin_tecla else ''}] oido: {texto!r}")
        if not texto:
            if not self.borrador and not self.tecla:
                self.pasa_a(DORMIDO)
            return

        if sin_tecla:
            # El detector abre la frase con el ruido del cuarto y lo que dices se pega
            # detras, asi que el nombre casi nunca cae en las primeras palabras.
            llamado, resto = palabra_clave.separa_nombre(texto, donde_sea=True)
            if llamado:
                texto = resto.strip()
            elif self.estado not in (RESPIRO, OYENDO):
                estado.apunta(f"{time.strftime('%H:%M:%S')}  sin el nombre, no se entrego")
                self.pasa_a(DORMIDO)
                return

        if texto:
            primera = texto.lower().split()[:1]
            if primera and primera[0].strip(",.") in ("escribe", "dicta", "teclea"):
                resto = texto.split(None, 1)[1] if " " in texto else ""
                estado.apunta(f"{time.strftime('%H:%M:%S')}  TECLEADO: {resto!r}")
                if resto and teclado.escribe(resto):
                    teclado.enter()
                self.pasa_a(DORMIDO)
                return
            with self.candado:
                self.borrador.append(texto)
            self.ultimo_texto = " ".join(self.borrador)
        # Todo lo que digas de corrido es UN mensaje: las frases se cortan por como
        # funciona whisper, no porque hayas terminado. Sale cuando te callas de verdad,
        # y de eso se encarga el vigilante.
        self.pasa_a(RESPIRO)

    def despacha(self):
        """Cierra tu mensaje, lo manda y le cede el turno al agente."""
        with self.candado:
            texto = " ".join(self.borrador).strip()
            self.borrador = []
        if not texto:
            self.pasa_a(DORMIDO)
            return
        self.ultimo_texto = texto
        self.pasa_a(PENSANDO)
        entregado = envio.envia(texto)
        estado.apunta(f"{time.strftime('%H:%M:%S')}  "
                      f"{'AL AGENTE' if entregado else 'NO SE ENTREGÓ'}: {texto!r}")
        if entregado:
            # Decir la verdad: si el agente trae cola, tu orden espera turno.
            estado.dice("encolado" if sesion.encolado() else "trabajando", vida=600)
        else:
            self.ultimo_texto = ("aprueba la carpeta: voz ver"
                                 if sesion.pide_confianza() else "el agente no está listo")
            self.pasa_a(DORMIDO)

    def sigue_trabajando(self):
        """Lo dice Claude Code, no la pantalla.

        Mirando el tmux se fallaba siempre: entre una herramienta y la siguiente el
        prompt reaparece un instante y se daba el turno por terminado, asi que el punto
        se apagaba a media faena y parecia que no habia hecho caso.

        Mandan sus hooks -`UserPromptSubmit` enciende la marca y `Stop` la apaga-, que
        son instantaneos. Y cada dos segundos se contrasta con `claude agents --json`,
        que es la via documentada para preguntarle por sus sesiones: si lo interrumpes
        con Escape, el hook de fin no llega a correr y la marca se quedaria encendida
        para siempre.
        """
        if config.HABLANDO.exists():
            return True
        marca = config.TRABAJANDO.exists()
        ahora = time.time()
        if marca and ahora - self.ultima_consulta > 2.0:
            self.ultima_consulta = ahora
            if sesion.estado_oficial() == "idle":
                config.TRABAJANDO.unlink(missing_ok=True)
                return False
        return marca

    # --- hilo MIRILLA: reconocerte el nombre EN VIVO -------------------------
    def mira(self):
        """Relee a media frase para contestar el nombre en el momento.

        Esperar a que la frase cierre son casi dos segundos hablandole sin ninguna
        senal de que te oye. Aqui se transcribe lo que llevas dicho y, en cuanto
        aparece el nombre, suena el tono y el punto se pone verde.
        """
        while self.vivo:
            time.sleep(config.MIRILLA)
            if self.estado != DORMIDO or self.tecla or not estado.escuchando():
                continue
            if not self.cortador.grabando or self.cortador.muestras < config.TASA * 0.7:
                continue
            if not self.turno_whisper.acquire(blocking=False):
                continue   # la frase ya cerrada siempre importa mas que el avance
            try:
                texto = self.transcriptor.texto_de(self.cortador.copia_parcial())
            finally:
                self.turno_whisper.release()
            if texto and palabra_clave.separa_nombre(texto, donde_sea=True)[0]:
                estado.tono("despierto")
                self.pasa_a(OYENDO)

    # --- hilo VIGILAR: los tiempos ------------------------------------------
    def vigila(self):
        lento = 0.0
        while self.vivo:
            time.sleep(0.2)
            if not estado.escuchando():
                continue
            ahora = time.time()
            # El pulso se publica SIEMPRE, no solo cuando algo cambia: la isla se
            # esconde sola si deja de recibirlo, y con la publicacion cada dos segundos
            # el punto se abria y se cerraba solo.
            self.late()

            # Empiece donde empiece, si esta leyendo en voz alta el microfono se cierra.
            if config.HABLANDO.exists() and self.estado not in (HABLANDO, OYENDO):
                self.pasa_a(HABLANDO)

            if self.estado == RESPIRO and not self.tecla and not self.cortador.grabando:
                # Si solo dijiste el nombre, el respiro es mas largo: dos segundos
                # no alcanzan para invocarlo y ponerse a hablar, y se cerraba el turno
                # antes de que empezaras.
                # El respiro se cuenta desde la ultima vez que se te OYO, no desde
                # que cambio el estado: diciendo el nombre y arrancando a hablar, el
                # turno se cerraba a media frase y lo que seguia se tiraba por no
                # llevar el nombre.
                espera = config.RESPIRO if self.borrador else config.ESPERA_ORDEN
                callado = time.time() - max(self.ultima_voz, self.desde)
                if self.pendientes.empty() and callado > espera:
                    self.despacha()

            elif self.estado == OYENDO and self.tecla and self.lleva > config.GRABACION_MAX:
                estado.apunta(f"{time.strftime('%H:%M:%S')}  dictado cerrado por el tope")
                self.sueltas()

            elif self.estado == PENSANDO:
                if config.HABLANDO.exists():
                    self.pasa_a(HABLANDO)
                elif self.lleva > config.TURNO_MAX:
                    # Algo se atoro; no dejarte sordo para siempre.
                    self.pasa_a(DORMIDO)
                elif self.lleva > 3.0 and not self.sigue_trabajando():
                    # Los primeros segundos el agente todavia se ve en su prompt aunque
                    # ya le llego el mensaje. Y el aviso se apaga AQUI: esperar a estar
                    # dormido para apagarlo era un nudo -no salia de pensando porque el
                    # aviso seguia, y el aviso seguia porque no salia de pensando-, y si
                    # lo interrumpias con Escape se quedaba trabajando para siempre.
                    estado.calla_dialogo()
                    self.pasa_a(DORMIDO)

            elif self.estado == HABLANDO and not config.HABLANDO.exists():
                # La cola de audio sigue sonando un instante despues de soltar la marca,
                # y entraba entera por el microfono.
                if self.lleva > config.ENFRIA:
                    self.pasa_a(DORMIDO)

            if ahora - lento < 2.0:
                continue
            lento = ahora
            if estado.dialogo() and not self.sigue_trabajando() and self.estado != PENSANDO:
                # Si interrumpes al agente con Escape, el hook que apaga el aviso nunca
                # corre. La pantalla del agente es la unica verdad.
                estado.calla_dialogo()
            # whisper ocupa ~2 GB de VRAM: sin usarse, que los suelte.
            if (self.transcriptor.vivo() and self.estado == DORMIDO
                    and ahora - self.ultimo_uso > config.VRAM_LIBRE_TRAS):
                self.transcriptor.detiene()
                estado.apunta(f"{time.strftime('%H:%M:%S')}  whisper dormido, VRAM libre")

    # --- lo que pinta la isla ----------------------------------------------
    def late(self, nivel=0.0):
        estado.publica(fase=self.estado, nivel=nivel, texto=self.ultimo_texto)


def _fuerza(frame):
    """Cuanto se movio el audio, de 0 a 1. Para la isla y para descartar el silencio."""
    if not frame:
        return 0.0
    picos = max(abs(int.from_bytes(frame[i:i + 2], "little", signed=True))
                for i in range(0, len(frame) - 1, 2))
    return min(1.0, picos / 12000)


def main():
    Asistente().corre()
