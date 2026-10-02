#!/usr/bin/env python3
"""Que responda a sus dos nombres y que NO despierte con palabras normales.

El falso positivo es el fallo mas molesto: el asistente se mete solo a media
conversacion. Y con "glados" es facil caer, porque suena a tres palabras que
salen todo el rato en una charla tecnica: grados, lados y helados.

Las frases de "lo que whisper escribio" no son inventadas: salieron de sintetizar
el nombre y pasarlo por el mismo whisper del proyecto.

  .venv/bin/python pruebas/nombres.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voz.escucha.palabra_clave import separa_nombre  # noqa: E402

DESPIERTAN = {
    "claudio": ["Claudio, abre el archivo", "claudio revisa esto", "Cloud, que hora es",
                "claudia ven", "glaudio hola", "Clodio, apaga"],
    "glados": ["GLaDOS, abre el archivo", "glados revisa esto", "Gladios, commitea",
               "Gladys, apaga el micro", "gla dos abre la terminal",
               "Gladoz, ya quedo?", "GLaDOS", "gladus borra eso", "gladis apaga",
               "gla 2 abre"],   # whisper escribe el "dos" en digito
}

CALLADO = [
    "estan a veinte grados", "los dos lados del archivo", "quiero helados",
    "claro que si", "en esa clase de casos", "la clave esta mal",
    "el audio se escucha mal", "son las dos", "todos los datos",
    "dame los grados de inclinacion", "por los dos lados", "el cuadro de mando",
    "de dos en dos", "mira los datos", "la dos esta rota", "subele dos grados",
    "el lado derecho", "cuadros de dialogo", "claramente no", "a ambos lados",
    "treinta grados centigrados", "dos por dos", "son las 2", "a 2 grados",
    # las que de verdad le dispararon el asistente a media conversacion
    "los lados estan mal", "ge lados por favor", "pla dos cosas", "cla dos veces",
]


def main():
    fallos = 0
    for esperado, frases in DESPIERTAN.items():
        for frase in frases:
            nombre, _ = separa_nombre(frase, donde_sea=True)
            if nombre != esperado:
                print(f"  FALLA  «{frase}» -> {nombre or 'no desperto'}, se esperaba {esperado}")
                fallos += 1
    for frase in CALLADO:
        nombre, _ = separa_nombre(frase, donde_sea=True)
        if nombre:
            print(f"  DESPIERTA SOLO  «{frase}» -> se creyo «{nombre}»")
            fallos += 1
    total = sum(len(v) for v in DESPIERTAN.values()) + len(CALLADO)
    print(f"{total - fallos}/{total} bien" if fallos else
          f"Bien: responde a sus {len(DESPIERTAN)} nombres en "
          f"{sum(len(v) for v in DESPIERTAN.values())} formas y se queda callado "
          f"en las {len(CALLADO)} frases que no lo llaman.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
