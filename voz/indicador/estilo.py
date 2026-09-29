"""Paleta y hoja de estilo de la isla. Separado para poder reteñirla sin tocar la logica."""

# Todo el estado cabe en un color y en si el punto late. Los rotulos se quitaron:
# se ven a diario, ya se saben de memoria y ocupaban mas que la informacion.
FASES = {
    "apagado":    ("#6b7280", False),   # asistente apagado; la tecla no hace nada
    "esperando":  ("#7c8797", False),   # listo: aprieta la tecla y habla
    "grabando":   ("#34d399", True),    # tienes la tecla apretada, te esta grabando
    "pensando":   ("#fbbf24", True),    # transcribiendo lo que dijiste
    "hablando":   ("#a78bfa", True),    # leyendo en voz alta
}

# Lo que hace el agente despues de recibir tu orden.
DIALOGO = {
    "trabajando": "#fbbf24",
    "responde":   "#a78bfa",
    "encolado":   "#f97316",
}

# La ventana DEBE quedar transparente: si no, el cuadro gris de GTK asoma por
# detras de las esquinas redondeadas y la isla se ve pegada sobre un parche.
CSS = b"""
window, window.background {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
}

.isla {
  background-color: alpha(#0e1014, 0.72);
  border: 1px solid alpha(#ffffff, 0.09);
  border-radius: 16px;
  padding: 6px 11px;
  box-shadow: 0 10px 28px alpha(#000000, 0.45);
}

.frase {
  font-family: "SF Pro Text", "Inter", "DejaVu Sans", sans-serif;
  font-size: 11px;
  color: alpha(#f2f4f8, 0.75);
}
"""
