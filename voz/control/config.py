"""Rutas y ajustes. Todo lo ajustable vive aqui."""
import os
from pathlib import Path

CASA = Path.home()
RAIZ = CASA / "Projects" / "voz"

# --- whisper.cpp (compilado con CUDA para la RTX 5070) ---
WHISPER = CASA / "Projects" / "voz-whisper"
WHISPER_SERVER = WHISPER / "build" / "bin" / "whisper-server"
MODELO = WHISPER / "models" / "ggml-large-v3-turbo.bin"
PUERTO = 8178
IDIOMA = "es"

# --- piper (voz sintetica en espanol) ---
PIPER = RAIZ / ".venv" / "bin" / "piper"
VOZ_MODELO = RAIZ / "voces" / "es_MX-claude-high.onnx"

# --- audio de entrada ---
TASA = 16000          # whisper solo come 16 kHz mono
MUESTRAS_FRAME = 512  # 32 ms por frame
MINIMO = 0.35         # segundos; por debajo de esto fue un roce de tecla, no una frase
COLCHON = 0.8         # segundos previos que se guardan, por si aprietas tarde
MUDO = 0.04           # por debajo de esto no hubo voz: whisper alucinaria una frase

# --- manos libres: deteccion de voz (Silero: reconoce voz humana, no volumen) ---
MODELO_VAD = RAIZ / "modelos" / "silero_vad.onnx"
VOZ_SEGURA = 0.70      # para ABRIR frase: alto, o el ruido lejano abre frases solo
VOZ_DUDOSA = 0.50      # mientras hablas, con esto basta para no cortarte
FRAMES_ARRANQUE = 2    # ~60 ms de voz seguida para abrir una frase
SILENCIO_CIERRE = 1.4  # silencio que cierra una frase corta
SILENCIO_LARGO = 2.4   # el que se exige cuando ya llevas rato hablando
FRASE_LARGA = 3.5      # a partir de aqui la frase cuenta como larga
ENUNCIADO_MAX = 8.0    # corte duro: con ruido continuo las frases largas salen vacias
RESPIRO = 2.0          # silencio que cierra TU mensaje; antes de eso sigue siendo el mismo
TURNO_MAX = 600.0      # tope del turno del agente, por si se atora y te deja sordo

# --- manos libres: la palabra de activacion ---
# CADA frase tiene que empezar con el nombre. Sin ventanas ni sesiones abiertas: eso fue
# lo que dejaba entrar los dialogos de un juego durante horas.
DESPIERTO = "claudio"
VARIANTES = ("claudio", "claudia", "clodio", "claudios", "cloudio", "glaudio",
             "claude", "clod", "cloud", "clau", "clode", "clot", "claud", "cloude",
             "clow", "gloud", "glod", "glaude", "glau")
# Palabras que se parecen al nombre pero NUNCA lo son: "audio" va dentro de "claudio" y
# Luis habla de audio a cada rato; "claro" era la otra que despertaba a media charla.
NO_ES_NOMBRE = ("audio", "claro", "clase", "clave", "cuadro", "aludio")

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
REGISTRO = CASA / ".local" / "state" / "voz.log"
