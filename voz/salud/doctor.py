"""Revisa el asistente y arregla lo que sepa arreglar.

Se corre de tres maneras y siempre es la misma pasada:

  voz doctor          a mano, con el informe en pantalla
  al arrancar         cuando entra la sesion o se reinicia el servicio
  al encender         cada vez que se prende con SUPER+ALT+M5 o `voz on`

Los dos automaticos van callados: solo escriben en `voz log` y avisan en pantalla si
algo quedo roto sin arreglo. Que se ponga a hablar de lo que ya funciona seria ruido.
"""
import time

from voz.control import config, estado
from voz.salud.revisiones import REVISIONES


class Contexto:
    """Lo que las revisiones necesitan saber de quien las manda correr.

    `dentro` distingue las dos situaciones: corriendo DENTRO del demonio no se puede
    revisar al demonio, y el transcriptor tiene que ser el suyo -si no, el doctor
    levanta un whisper que el demonio no conoce y acaban dos peleando por el puerto-.
    """

    def __init__(self, transcriptor=None, dentro=False):
        self.dentro = dentro
        if transcriptor is None:
            from voz.transcripcion.whisper_local import Transcriptor
            transcriptor = Transcriptor()
        self.transcriptor = transcriptor


def revisa(ctx=None, avisa=None):
    """Corre todas las revisiones. Devuelve la lista de (nombre, queja, arreglo).

    `arreglo` es lo que se hizo, None si no habia nada que hacer y "" si se sabia que
    estaba mal pero no se pudo arreglar.
    """
    ctx = ctx or Contexto()
    informe = []
    for nombre, mira, repara in REVISIONES:
        try:
            queja = mira(ctx)
        except Exception as falla:
            queja = f"no se pudo revisar: {falla!r}"
            repara = None
        if not queja:
            informe.append((nombre, None, None))
            if avisa:
                avisa(nombre, None, None)
            continue
        arreglo = ""
        if repara:
            try:
                arreglo = repara(ctx) or ""
            except Exception as falla:
                arreglo = ""
                queja += f" (fallo el arreglo: {falla!r})"
        informe.append((nombre, queja, arreglo))
        if avisa:
            avisa(nombre, queja, arreglo)
    return informe


def en_silencio(ctx=None, motivo="revision"):
    """La pasada automatica. Al log siempre; a la pantalla solo si quedo algo roto."""
    informe = revisa(ctx)
    for nombre, queja, arreglo in informe:
        if queja:
            estado.apunta(f"{time.strftime('%H:%M:%S')}  doctor ({motivo}) {nombre}: "
                          f"{queja} -> {arreglo or 'SIN ARREGLO'}")
    rotos = [n for n, queja, arreglo in informe if queja and not arreglo]
    if rotos:
        estado.avisa("Voz: revisa " + ", ".join(rotos),
                     "Corre `voz doctor` para ver el detalle", "critical")
    return informe


def informe_en_pantalla():
    """`voz doctor`: una linea por revision, y al final que hacer si algo sigue mal."""
    from voz.habla import catalogo
    encendido = config.ESCUCHANDO.exists()
    # Cual es la voz va en la cabecera y no en una revision: lo normal es que este
    # bien, y lo que hacia falta era poder VERLO sin que nada estuviera roto.
    print(f"Asistente {'ENCENDIDO' if encendido else 'apagado'}. "
          f"Voz: {catalogo.actual().stem}. Revisando...\n")

    def pinta(nombre, queja, arreglo):
        if not queja:
            print(f"  ok   {nombre}")
        elif arreglo:
            print(f"  ARREGLADO  {nombre}: {queja} -> {arreglo}")
        else:
            print(f"  FALLA      {nombre}: {queja}")

    informe = revisa(avisa=pinta)
    rotos = [n for n, queja, arreglo in informe if queja and not arreglo]
    arreglados = [n for n, queja, arreglo in informe if queja and arreglo]
    print()
    if not rotos and not arreglados:
        print("Todo en orden.")
    elif not rotos:
        print("Arreglado: " + ", ".join(arreglados) + ". Ya se puede usar.")
    else:
        print("Sin arreglo: " + ", ".join(rotos))
        print("Eso se ve a mano en docs/cuando-falla.md")
    return 1 if rotos else 0
