"""Corta el audio en frases: abre cuando empiezas a hablar y cierra cuando callas."""
from collections import deque

from voz.control import config
from voz.escucha.voz_humana import VozHumana


class CortadorDeVoz:
    """Se le empujan frames; devuelve el audio de la frase cuando esta cerrada."""

    def __init__(self):
        self.voz = VozHumana()
        # Guarda SIEMPRE el ultimo segundo: cuando Silero confirma que hablas, las
        # primeras silabas ya pasaron, y sin este colchon la frase entra decapitada.
        self.colchon = deque(maxlen=int(config.COLCHON * config.TASA / config.MUESTRAS_FRAME) + 1)
        self.reinicia()

    def reinicia(self):
        self.grabando = False
        self.frase = bytearray()
        self.arranque = 0
        self.silencio = 0
        self.probabilidad = 0.0
        self.voz.reinicia()
        self.colchon.clear()

    @property
    def muestras(self):
        return len(self.frase) / 2

    @property
    def avance_cierre(self):
        """De 0 a 1, cuanto llevas del silencio que cierra la frase. Para la isla."""
        if not self.grabando:
            return 0.0
        return min(1.0, self.silencio / self._silencio_necesario())

    def _silencio_necesario(self):
        """Mas margen en frases largas: al dictar parrafos se hacen pausas mas hondas."""
        largo = self.muestras / config.TASA > config.FRASE_LARGA
        segundos = config.SILENCIO_LARGO if largo else config.SILENCIO_CIERRE
        return segundos * config.TASA / config.MUESTRAS_FRAME

    def copia_parcial(self):
        return bytes(self.frase)

    def empuja(self, frame):
        """Devuelve el audio de la frase si acaba de cerrarse; si no, None."""
        self.probabilidad = self.voz.probabilidad(frame)
        hay_voz = self.probabilidad >= config.VOZ_SEGURA

        if not self.grabando:
            self.colchon.append(frame)
            self.arranque = self.arranque + 1 if hay_voz else 0
            if self.arranque >= config.FRAMES_ARRANQUE:
                self.grabando = True
                self.frase = bytearray(b"".join(self.colchon))
                self.colchon.clear()
                self.silencio = 0
            return None

        self.frase += frame
        # Mientras hablas basta con la sospecha: exigir certeza en cada frame cortaba
        # la frase en las consonantes sordas, a media palabra.
        if self.probabilidad >= config.VOZ_DUDOSA:
            self.silencio = 0
        else:
            self.silencio += 1

        if self.silencio >= self._silencio_necesario():
            frase = bytes(self.frase)
            self.reinicia()
            return frase
        if self.muestras / config.TASA > config.ENUNCIADO_MAX:
            frase = bytes(self.frase)
            self.reinicia()
            return frase
        return None
