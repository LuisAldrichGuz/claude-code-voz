"""Deja hablable la respuesta de Claude Code: fuera markdown, codigo y rutas kilometricas.

Sin esto el TTS te lee 200 lineas de Python y los guiones de las vinetas una por una.
"""
import re

_BLOQUE_CODIGO = re.compile(r"```.*?```", re.DOTALL)
_CODIGO_CORTO = re.compile(r"`([^`]+)`")
_ENLACE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_ADORNO = re.compile(r"[*_#>]+")
_RUTA = re.compile(r"(?:~|/)[\w./~-]{12,}")
_ESPACIOS = re.compile(r"\s+")

LIMITE = 600  # caracteres; mas que esto y te esta leyendo un ensayo


def limpia(texto, limite=LIMITE):
    """Markdown crudo -> frase que suena bien en voz alta."""
    texto = _BLOQUE_CODIGO.sub(" bloque de codigo. ", texto)
    texto = _ENLACE.sub(r"\1", texto)
    texto = _CODIGO_CORTO.sub(r"\1", texto)
    texto = _RUTA.sub(" la ruta ", texto)
    texto = _ADORNO.sub("", texto)
    texto = re.sub(r"^\s*[-•]\s*", "", texto, flags=re.MULTILINE)
    texto = _ESPACIOS.sub(" ", texto).strip()

    if len(texto) <= limite:
        return texto
    # Corta en el ultimo punto que quepa, para no dejar la frase colgando.
    recorte = texto[:limite]
    punto = recorte.rfind(". ")
    return (recorte[:punto + 1] if punto > limite // 3 else recorte) + " Te dejo el resto escrito."
