"""Reconoce con cual de sus nombres lo llamaste y separa la orden que sigue.

Whisper no escribe el nombre igual dos veces, asi que no se compara literal: se normaliza
y se acepta cualquier forma parecida. Responde a DOS nombres, "claudio" y "glados", y en
config.NOMBRES esta cada uno con las formas en que whisper lo suele escribir. No es
"claude" por esto mismo: transcribe en espanol y le salia "claro" o "cloud", y "claro" es
palabra comun -aceptarla despertaba al asistente a media conversacion-.

Se devuelve CUAL de los dos nombre se oyo, no un si o un no, para que en el registro
quede con cual lo despertaron y se pueda depurar cual de los dos falla.
"""
import difflib
import re
import unicodedata

from voz.control import config

_BASURA = re.compile(r"[^\w\s]", re.UNICODE)


def normaliza(texto):
    """minusculas, sin acentos y sin puntuacion: 'Claudio, ¿abres?' -> 'claudio abres'.

    El "2" se escribe como palabra porque whisper oye "GLaDOS" y transcribe "Gela 2":
    la segunda mitad del nombre le suena al numero y lo pone en digito.
    """
    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return _BASURA.sub(" ", plano).replace("2", "dos").strip()


def forma_conocida(palabra):
    """El nombre al que corresponde esa forma EXACTA, o None. Sin parecidos."""
    if palabra in config.NO_ES_NOMBRE:
        return None
    for nombre, como_suena in config.NOMBRES.items():
        if palabra in como_suena["variantes"]:
            return nombre
    return None


def cual_nombre(palabra):
    """Con cual de sus nombres lo llamaron, o None si esa palabra no es ninguno."""
    # Primero las formas exactas: valen aunque sean cortas o se parezcan a algo comun.
    nombre = forma_conocida(palabra)
    if nombre:
        return nombre
    if palabra in config.NO_ES_NOMBRE or len(palabra) < 4:
        return None
    # Y luego por parecido, para el nombre que lo admita. Se compara contra TODAS sus
    # formas largas y no solo contra el nombre: whisper oye "gloud", que se parece a
    # "cloud" y no a "claudio". Las formas de cuatro letras quedan fuera -son tan cortas
    # que "claro" les pegaria- y solo valen exactas.
    for nombre, como_suena in config.NOMBRES.items():
        umbral = como_suena["parecido"]
        formas = [f for f in como_suena["variantes"] if len(f) >= 5]
        if umbral and formas and max(difflib.SequenceMatcher(None, palabra, f).ratio()
                                     for f in formas) >= umbral:
            return nombre
    return None


def separa_nombre(texto, donde_sea=False):
    """Devuelve (con_que_nombre, resto). El nombre es None si no te llamaron.

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
        nombre = cual_nombre(normaliza(palabra))
        if nombre:
            return nombre, " ".join(palabras[i + 1:]).lstrip(" ,.;:")
        # Whisper parte el nombre en dos ("gla dos", "cla dos") porque la segunda
        # mitad le suena a una palabra que conoce. Se prueba tambien pegado, pero
        # EXIGIENDO forma exacta: con parecido, "el audio" pega con "glaudio" y
        # "las dos" con "glados", y despertaba a media conversacion.
        if i + 1 < len(palabras):
            pegadas = normaliza(palabra) + normaliza(palabras[i + 1])
            nombre = forma_conocida(pegadas)
            if nombre:
                return nombre, " ".join(palabras[i + 2:]).lstrip(" ,.;:")
    return None, texto
