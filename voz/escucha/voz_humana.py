"""Silero VAD: dice si un trozo de audio es una persona hablando.

Medir volumen no sirve en este cuarto: con un video puesto el ruido abre frases solo y
la tuya no cierra nunca. Silero distingue voz de ruido, que es otra cosa.
"""
import numpy as np
import onnxruntime

from voz.control import config


class VozHumana:
    """Devuelve, por cada frame de 32 ms, la probabilidad de que sea voz (0 a 1)."""

    def __init__(self):
        opciones = onnxruntime.SessionOptions()
        opciones.log_severity_level = 4          # el modelo avisa de cosas que no importan
        opciones.inter_op_num_threads = 1
        opciones.intra_op_num_threads = 1
        self.sesion = onnxruntime.InferenceSession(
            str(config.MODELO_VAD), opciones, providers=["CPUExecutionProvider"])
        self.reinicia()

    def reinicia(self):
        """Olvida lo anterior. Cada frase empieza limpia o arrastra el estado de la previa."""
        self.estado = np.zeros((2, 1, 128), dtype=np.float32)

    def probabilidad(self, frame):
        muestras = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        if len(muestras) != config.MUESTRAS_FRAME:
            return 0.0
        salida, self.estado = self.sesion.run(
            None, {"input": muestras.reshape(1, -1),
                   "state": self.estado,
                   "sr": np.array(config.TASA, dtype=np.int64)})
        return float(salida[0][0])
