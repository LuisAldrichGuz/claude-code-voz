"""Rutas y ajustes. Todo lo ajustable vive aqui."""
import os
from pathlib import Path

CASA = Path.home()
# La raiz se deduce del propio archivo: asi el proyecto se puede clonar donde sea.
RAIZ = Path(__file__).resolve().parents[2]

# --- whisper.cpp (compilado con CUDA para la RTX 5070) ---
WHISPER = Path(os.environ.get("VOZ_WHISPER", RAIZ.parent / "voz-whisper"))
WHISPER_SERVER = WHISPER / "build" / "bin" / "whisper-server"
MODELO = WHISPER / "models" / "ggml-large-v3-turbo.bin"
PUERTO = 8178
IDIOMA = "es"

# --- piper (voz sintetica en espanol) ---
PIPER = RAIZ / ".venv" / "bin" / "piper"
# Que voz habla se elige con `voz motor`; ver voz/habla/catalogo.py.
# A cuanto se reproduce. 1.0 es lo que saca piper, que llega a escala completa.
# Medido en esta maquina: con EasyEffects cargando su preset "Headphones"
# -compresor con makeup +8 dB y limitador con entrada +4 dB y techo -1.5 dB-, todo
# lo que salga por encima de 0.55 aprox. llega al limitador pegado al techo y se
# oye apretado. Bajar esto lo limpia a costa de volumen; la causa de fondo esta en
# el preset, que es de Luis y no se toca desde aqui.
VOZ_VOLUMEN = 1.0

# --- audio de entrada ---
TASA = 16000          # whisper solo come 16 kHz mono
MUESTRAS_FRAME = 512  # 32 ms por frame
MINIMO = 0.35         # segundos; por debajo de esto fue un roce de tecla, no una frase
COLCHON = 0.8         # segundos previos que se guardan, por si aprietas tarde
MUDO = 0.04           # por debajo de esto no hubo voz: whisper alucinaria una frase

# --- manos libres: deteccion de voz (Silero: reconoce voz humana, no volumen) ---
MODELO_VAD = RAIZ / "modelos" / "silero_vad.onnx"
VOZ_SEGURA = 0.60      # para ABRIR frase; mas bajo, oye sin que tengas que gritar
VOZ_DUDOSA = 0.35      # mientras hablas, con esto basta para no cortarte
FRAMES_ARRANQUE = 2    # ~60 ms de voz seguida para abrir una frase
SILENCIO_CIERRE = 1.4  # silencio que cierra una frase corta
SILENCIO_LARGO = 2.4   # el que se exige cuando ya llevas rato hablando
FRASE_LARGA = 3.5      # a partir de aqui la frase cuenta como larga
ENUNCIADO_MAX = 20.0   # corte duro de UNA frase; el mensaje se sigue juntando entero
RESPIRO = 2.5          # silencio que cierra TU mensaje; antes de eso sigue siendo el mismo
MIRILLA = 0.7          # cada cuanto se relee lo que llevas dicho, para contestarte ya
ESPERA_ORDEN = 3.0     # tras invocarlo a secas, lo que espera a que arranques
TURNO_MAX = 600.0      # tope del turno del agente, por si se atora y te deja sordo
RECUERDA = 90.0        # turno largo: cada tanto dice que sigue en eso
ENFRIA = 1.5           # sordo un momento tras callarse: la cola de audio sigue sonando

# --- manos libres: como se le llama ---
# CADA frase tiene que empezar con uno de sus nombres. Sin ventanas ni sesiones
# abiertas: eso fue lo que dejaba entrar los dialogos de un juego durante horas.
#
# Para cada nombre van las formas en que whisper lo escribe de verdad, que casi
# nunca son el nombre bien puesto: transcribe en espanol y lo que oye lo acomoda a
# palabras que conoce. Se compara contra estas formas, no contra el nombre bonito.
# "parecido" es cuanto se acepta de aproximacion para formas que no estan en la
# lista; None significa que SOLO valen las exactas.
#
# "claudio" aguanta aproximacion: es largo y no choca con nada comun. "glados" no,
# y esta medido: contra sus propias formas, "glado" -que es una transcripcion real-
# puntua 0.909, y "lados" -palabra normal- puntua 0.909 tambien. Identico. Cualquier
# umbral o deja entrar "los dos lados" o rechaza transcripciones buenas, asi que
# para ese nombre se confia solo en la lista, y crece cuando el registro enseñe una
# forma nueva (ver docs/cuando-falla.md).
NOMBRES = {
    "claudio": {
        "parecido": 0.75,
        "variantes": ("claudio", "claudia", "clodio", "claudios", "cloudio",
                      "glaudio", "claude", "clod", "cloud", "clau", "clode",
                      "clot", "claud", "cloude", "clow", "gloud", "glod",
                      "glaude", "glau"),
    },
    # Solo formas que NO existen como palabra en espanol, ni se parecen a una por
    # una letra. Fuera quedaron "glado", "plados", "clados", "gelados" y "geladas":
    # todas caen a un paso de "lado", "lados" o "helados", y una de ellas ya le
    # desperto el asistente a media conversacion.
    #
    # El criterio, que no se relaje: mas vale que a veces NO despierte y haya que
    # repetir el nombre, a que despierte solo. Un falso positivo le interrumpe lo
    # que esta haciendo; un falso negativo cuesta decirlo otra vez.
    "glados": {
        "parecido": None,
        "variantes": ("glados", "gladios", "gladoz", "gladus", "gladys", "gladis",
                      "gladdos", "gladox", "gladosh", "gladoss", "glaods"),
    },
}

# Palabras que se parecen a algun nombre pero NUNCA lo son. Sin esta lista el
# asistente despierta solo a media charla, que es el fallo mas molesto de todos.
# "audio" va dentro de "claudio" y sale a cada rato hablando de esto mismo, y
# "claro" es de las palabras mas comunes del idioma. Las de "glados" son todas
# normales en una charla tecnica: grados de temperatura, los dos lados de algo.
NO_ES_NOMBRE = ("audio", "claro", "clase", "clave", "cuadro", "cuadros", "aludio",
                "grados", "lados", "lado", "helados", "dos", "todos", "datos")

# --- tiempos ---
VRAM_LIBRE_TRAS = 900.0   # sin usarse, whisper suelta sus ~2 GB de VRAM
GRABACION_MAX = 180.0     # tope por si la tecla se queda trabada

# --- estado en disco (se borra al reiniciar la maquina) ---
RUN = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "voz"
PID = RUN / "daemon.pid"
ESCUCHANDO = RUN / "escuchando"   # existe = asistente encendido
PULSO = RUN / "pulso.json"        # lo que el indicador pinta
DIALOGO = RUN / "dialogo.json"    # lo que el agente esta haciendo o contestando
HABLANDO = RUN / "hablando"       # existe = el TTS esta sonando
TRABAJANDO = RUN / "trabajando"   # existe = el agente esta a media respuesta
REGISTRO = CASA / ".local" / "state" / "voz.log"
