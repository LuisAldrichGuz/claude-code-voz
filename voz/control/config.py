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
COLCHON = 0.5         # segundos previos que se guardan, por si aprietas tarde
MUDO = 0.04           # por debajo de esto no hubo voz: whisper alucinaria una frase

# --- tiempos ---
VRAM_LIBRE_TRAS = 300.0   # sin usarse, whisper suelta sus ~2 GB de VRAM
GRABACION_MAX = 180.0     # tope por si la tecla se queda trabada

# --- estado en disco (se borra al reiniciar la maquina) ---
RUN = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "voz"
PID = RUN / "daemon.pid"
ESCUCHANDO = RUN / "escuchando"   # existe = asistente encendido
PULSO = RUN / "pulso.json"        # lo que el indicador pinta
DIALOGO = RUN / "dialogo.json"    # lo que el agente esta haciendo o contestando
HABLANDO = RUN / "hablando"       # existe = el TTS esta sonando
REGISTRO = CASA / ".local" / "state" / "voz.log"
