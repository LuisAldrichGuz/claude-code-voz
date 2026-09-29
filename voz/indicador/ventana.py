"""Isla flotante que muestra si el asistente te esta oyendo.

Ventana propia sobre el compositor (layer-shell), no una notificacion del sistema:
no depende de mako ni de como esten configuradas las notificaciones.
Aparece al encender el micro y se va al apagarlo.
"""
import math
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, Gtk4LayerShell as Capa  # noqa: E402

from voz.control import estado  # noqa: E402
from voz.habla import piper_voz  # noqa: E402
from voz.indicador import estilo  # noqa: E402

PUNTO = 9          # diametro del circulito de estado, en px
COLA = 1.2         # segundos que la isla se queda despues de terminar
DESVANECE = 0.35   # segundos del fundido de salida
ANCHO_TEXTO = 40   # caracteres antes de partir renglon
LINEAS_MAX = 3     # mas que esto ya es un panel, no un aviso
MARGEN = 12        # separacion de la esquina

# Solo estas fases justifican tapar pantalla: cuando de verdad te esta atendiendo.
ACTIVAS = ("oyendo", "grabando", "pensando", "hablando")


class Punto(Gtk.DrawingArea):
    """Circulito de color con un halo que late cuando esta activo."""

    def __init__(self):
        super().__init__()
        self.set_content_width(PUNTO * 2)
        self.set_content_height(PUNTO * 2)
        self.set_valign(Gtk.Align.CENTER)
        self._color = (0.42, 0.45, 0.50)
        self._late = False
        self._fase = 0.0
        self.set_draw_func(self._pinta)

    def actualiza(self, color_hex, late):
        self._color = _a_rgb(color_hex)
        self._late = late
        self._fase += 0.16
        self.queue_draw()

    def _pinta(self, _area, cr, ancho, alto, *_):
        cx, cy = ancho / 2, alto / 2
        r, g, b = self._color
        if self._late:
            pulso = 0.5 + 0.5 * math.sin(self._fase)
            cr.set_source_rgba(r, g, b, 0.16 + 0.16 * pulso)
            cr.arc(cx, cy, PUNTO * (0.85 + 0.30 * pulso), 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgb(r, g, b)
        cr.arc(cx, cy, PUNTO / 2, 0, 2 * math.pi)
        cr.fill()


class Isla(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self._arma_capa()

        # Lo minimo que dice algo: un punto de color. El rotulo sobraba -"pensando",
        # "Claude responde"- porque se ve a diario y ya se sabe de memoria; el color
        # lo dice igual y no ocupa media pantalla. La frase solo sale mientras dictas,
        # que es la unica que hay que poder leer antes de que se mande.
        fila = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fila.add_css_class("isla")

        self.punto = Punto()
        fila.append(self.punto)

        # width_chars, no solo max_width_chars: al pedirle a la ventana que se
        # remidiera, el minimo de un label que parte por palabras es UNA letra, y la
        # frase salia en columna de dos caracteres. Asi el ancho es el mismo siempre.
        self.frase = Gtk.Label(xalign=0, width_chars=ANCHO_TEXTO,
                               max_width_chars=ANCHO_TEXTO, wrap=True,
                               lines=LINEAS_MAX, ellipsize=Pango.EllipsizeMode.END)
        self.frase.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.frase.set_valign(Gtk.Align.CENTER)
        self.frase.add_css_class("frase")
        fila.append(self.frase)

        # Picarle a la pastilla lo calla: interrumpir no deberia obligarte a hablar.
        clic = Gtk.GestureClick()
        clic.connect("pressed", self._callar)
        fila.add_controller(clic)

        self.set_child(fila)
        self._hasta = 0.0        # momento en que se debe ir
        self._ancho_previo = None
        GLib.timeout_add(40, self.late)

    def _muestra_frase(self, texto):
        """La ventana NO encoge sola al quitar el texto: se queda con el ancho mas
        grande que haya tenido y deja una pastilla larga y vacia en la esquina.
        Pidiendole el tamano minimo se vuelve a medir contra lo que hay ahora."""
        if texto == self._ancho_previo:
            return
        aparece = bool(texto) != bool(self._ancho_previo)
        self._ancho_previo = texto
        self.frase.set_text(texto)
        self.frase.set_visible(bool(texto))
        if aparece:
            self.set_default_size(1, 1)

    def _callar(self, *_):
        piper_voz.callate()
        estado.calla_dialogo()

    def _arma_capa(self):
        """Arriba a la derecha, sin robar el teclado ni reservar espacio."""
        Capa.init_for_window(self)
        Capa.set_layer(self, Capa.Layer.OVERLAY)
        Capa.set_anchor(self, Capa.Edge.TOP, True)
        Capa.set_anchor(self, Capa.Edge.RIGHT, True)
        Capa.set_margin(self, Capa.Edge.TOP, MARGEN)
        Capa.set_margin(self, Capa.Edge.RIGHT, MARGEN)
        Capa.set_keyboard_mode(self, Capa.KeyboardMode.NONE)
        Capa.set_namespace(self, "voz-indicador")

    def late(self):
        """Lee el pulso del demonio y se repinta, 25 veces por segundo."""
        p = estado.pulso()
        fase = p.get("fase", "apagado")
        ahora = time.monotonic()

        # Como Siri: no vive en pantalla. Solo sale mientras te atiende - grabando,
        # transcribiendo, leyendo - y se desvanece. Antes tambien asomaba a cada
        # cambio de estado, para confirmar la tecla; eso dejaba un punto gris
        # apareciendo sin que hubieras hecho nada. Encender y apagar ya lo dice el
        # OSD del sistema.
        charla = estado.dialogo()

        if charla or fase in ACTIVAS:
            self._hasta = ahora + COLA

        restante = self._hasta - ahora
        if restante <= 0:
            self.set_visible(False)
            return True
        self.set_visible(True)
        self.set_opacity(1.0 if restante > DESVANECE else restante / DESVANECE)

        color, late = estilo.FASES.get(fase, estilo.FASES["esperando"])
        if charla and fase not in ("grabando", "pensando"):
            color = estilo.DIALOGO.get(charla["estado"], estilo.DIALOGO["trabajando"])
            late = True
            self.punto.actualiza(color, late)
            self._muestra_frase("")   # lo que contesto se oye, no se lee
            return True
        self.punto.actualiza(color, late)
        # Solo lo que dijiste tu: la respuesta se oye, no se lee.
        dictando = fase in ("grabando", "pensando")
        self._muestra_frase((p.get("texto") or "").strip() if dictando else "")
        return True


def _a_rgb(hexa):
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def main():
    app = Gtk.Application(application_id="net.luisaldrichguz.voz")

    def arranca(a):
        hoja = Gtk.CssProvider()
        hoja.load_from_data(estilo.CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), hoja, 800)
        Isla(a).present()

    app.connect("activate", arranca)
    app.run([])


if __name__ == "__main__":
    main()
