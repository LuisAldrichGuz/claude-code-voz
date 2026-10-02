#!/usr/bin/env python3
"""Que ningun bloque se lea DOS veces cuando los dos hooks corren a la vez.

Es el bug que vuelve: hay dos hooks que hablan -`lee_avance.py` en PostToolUse y
`lee_respuesta.py` en Stop- y lo unico que los coordina es la marca de leido. En
cuanto uno mira la marca y el otro la escribe en medio, los dos se llevan el
mismo bloque y a Luis se lo cuentan dos veces.

Se provoca el caso de verdad: un turno con varias herramientas seguidas y texto
entre medias, con los dos hooks disparando encima. Nada suena -se cambia la voz
por un cuaderno- y nada toca el estado de la sesion: la marca y las senales van a
una carpeta de usar y tirar.

  .venv/bin/python pruebas/no_repite.py                 arreglado: tiene que pasar
  .venv/bin/python pruebas/no_repite.py --sin-candado   roto a proposito: tiene que fallar

Es una carrera, asi que detectarla es cuestion de suerte: medido, el modo roto
falla 4 de cada 5 veces y el arreglado 0 de 5. Si alguna vez falla el arreglado,
aunque sea una, es un bug de verdad y no ruido.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

BLOQUES = [
    "Voy a revisar los tres archivos.",
    "Listo el primero, sigo con el segundo.",
    "El segundo tenia un import de mas, ya lo quite.",
    "Ya quedaron los tres. Los tests pasan.",
]
VUELTAS = 10         # hooks disparados por bloque; con pocos la carrera no sale


def _transcript(ruta, bloques):
    """Un turno como los de verdad: texto, herramientas, texto, herramientas..."""
    lineas = [{"type": "user", "message": {"content": "revisa los tres archivos"}}]
    for i, texto in enumerate(bloques):
        lineas.append({"type": "assistant",
                       "message": {"content": [{"type": "text", "text": texto}]}})
        for _ in range(2):      # las herramientas de en medio, que son las que disparan
            lineas.append({"type": "assistant",
                           "message": {"content": [{"type": "tool_use", "id": f"t{i}"}]}})
            lineas.append({"type": "user",
                           "message": {"content": [{"type": "tool_result", "id": f"t{i}"}]}})
    ruta.write_text("\n".join(json.dumps(l) for l in lineas))


def _corre_hook():
    """Modo interno: corre UN hook de verdad, con la voz cambiada por un cuaderno."""
    cual, evento, cuaderno, sin_candado, arranque = sys.argv[2:7]
    import contextlib
    import time


    from voz.agentes import sesion
    from voz.claude_code import leido
    from voz.control import estado
    from voz.habla import piper_voz

    sesion.ventana_actual = lambda: sesion.MAESTRO
    estado.escuchando = lambda: True
    estado.dice = lambda *a, **k: None
    estado.calla_dialogo = lambda *a, **k: None
    estado.apunta = lambda *a, **k: None
    if sin_candado == "si":
        leido.turno = contextlib.nullcontext      # el bug, a proposito

    def apunta_lo_dicho(texto, limpiar=True):
        with open(cuaderno, "a") as f:            # append: dos procesos no se pisan
            f.write(json.dumps(texto) + "\n")
        time.sleep(0.3)                           # hablar tarda; sin esto no hay carrera
        return True
    piper_voz.di = apunta_lo_dicho

    with open(evento) as f:
        entrada = f.read()
    sys.stdin = __import__("io").StringIO(entrada)
    if cual == "avance":
        from voz.claude_code.lee_avance import main
    else:
        from voz.claude_code.lee_respuesta import main

    # Barrera, y va AQUI: si se espera antes de importar, cada proceso tarda lo
    # suyo en cargar los modulos y se vuelven a escalonar. Con todo ya cargado,
    # entran de verdad a la vez y la carrera sale.
    espera = float(arranque) - time.time()
    if espera > 0:
        time.sleep(espera)
    return main()


def main():
    sin_candado = "--sin-candado" in sys.argv
    with tempfile.TemporaryDirectory(prefix="voz-prueba-") as taller:
        taller = Path(taller)
        transcript = taller / "transcript.jsonl"
        evento = taller / "evento.json"
        cuaderno = taller / "dicho.jsonl"
        cuaderno.touch()
        evento.write_text(json.dumps({"transcript_path": str(transcript)}))

        entorno = dict(os.environ,
                       VOZ_MARCA=str(taller / "leido.json"),
                       XDG_RUNTIME_DIR=str(taller))

        # El transcript va creciendo, como en un turno real, y en cada crecida se
        # disparan los hooks encimados.
        import time
        for i in range(1, len(BLOQUES) + 1):
            _transcript(transcript, BLOQUES[:i])
            arranque = time.time() + 1.2          # el instante en que entran todos
            procesos = [
                subprocess.Popen(
                    [sys.executable, __file__, "--hook",
                     "avance" if vuelta % 2 == 0 else "respuesta", str(evento),
                     str(cuaderno), "si" if sin_candado else "no", str(arranque)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=entorno)
                for vuelta in range(VUELTAS)]
            for p in procesos:
                p.wait()

        dicho = [json.loads(l) for l in cuaderno.read_text().splitlines() if l.strip()]
        locuciones = len(dicho)

    veces = {b: sum(b in d for d in dicho) for b in BLOQUES}
    for bloque, n in veces.items():
        estado = "ok" if n == 1 else ("NUNCA" if n == 0 else f"{n} VECES")
        print(f"  {estado:>8s}  {bloque}")
    print(f"  ({locuciones} locuciones de {len(BLOQUES) * VUELTAS} hooks)")
    repetidos = [b for b, n in veces.items() if n > 1]
    perdidos = [b for b, n in veces.items() if n == 0]
    print()
    if repetidos:
        print(f"FALLA: {len(repetidos)} bloque(s) se leyeron mas de una vez.")
        return 1
    if perdidos:
        print(f"FALLA: {len(perdidos)} bloque(s) no se leyeron nunca.")
        return 1
    print(f"Bien: los {len(BLOQUES)} bloques se leyeron una sola vez, "
          f"con {len(BLOQUES) * VUELTAS} hooks encimados.")
    return 0


if __name__ == "__main__":
    sys.exit(_corre_hook() if "--hook" in sys.argv else main())
