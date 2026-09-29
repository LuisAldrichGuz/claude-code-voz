"""Reconoce el nombre al principio de lo que dijiste y separa la orden que sigue.

Whisper no escribe el nombre igual dos veces, asi que no se compara literal: se normaliza
y se acepta cualquier forma parecida. El nombre es "Claudio" y no "Claude" por esto mismo:
whisper transcribe en espanol y "Claude" le salia "Claro" o "Cloud", y "Claro" es palabra
comun -aceptarla despertaba al asistente a media conversacion-.
"""
import difflib
import re
import unicodedata

from voz.control import config

_BASURA = re.compile(r"[^\w\s]", re.UNICODE)


def normaliza(texto):
    """minusculas, sin acentos y sin puntuacion: 'Claudio, ¿abres?' -> 'claudio abres'."""
    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return _BASURA.sub(" ", plano).strip()


def suena_al_nombre(palabra):
    """True si la palabra se parece lo bastante al nombre."""
    if palabra in config.VARIANTES:
        return True
    if palabra in config.NO_ES_NOMBRE or len(palabra) < 4:
        return False
    # Se compara contra TODAS las formas largas conocidas y no solo contra "claudio":
    # whisper oye "gloud", que se parece a "cloud" y no a "claudio". Las variantes de
    # cuatro letras quedan fuera del parecido -son tan cortas que "claro" les pegaria- y
    # solo valen por coincidencia exacta. El corte es 0.75: con 0.72 despertaba con "clase".
    formas = [config.DESPIERTO] + [v for v in config.VARIANTES if len(v) >= 5]
    return max(difflib.SequenceMatcher(None, palabra, f).ratio() for f in formas) >= 0.75


def separa_nombre(texto, donde_sea=False):
    """Devuelve (te_llamaron, resto).

    Normalmente el nombre solo cuenta en las primeras tres palabras: asi "Claudio, borra
    esto" despierta y "el codigo de Claudio esta raro" no.

    Con `donde_sea` se busca en toda la frase, y eso es lo que hace falta sin la tecla:
    con una tele o un juego sonando, el detector de voz abre la frase con el ruido y lo
    que tu dices se pega DETRAS, asi que tu nombre nunca cae en las primeras palabras y
    no pasaba nada por mas veces que lo dijeras. Se entrega lo que va despues del nombre.
    """
    palabras = texto.split()
    ventana = len(palabras) if donde_sea else 3
    for i, palabra in enumerate(palabras[:ventana]):
        if suena_al_nombre(normaliza(palabra)):
            return True, " ".join(palabras[i + 1:]).lstrip(" ,.;:")
    return False, texto
