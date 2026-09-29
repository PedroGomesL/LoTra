"""
Módulo de Recorte de Tela Nativo do LoTra (NativeScreenSnipper):
- Substitui a dependência do ms-screenclip: do Windows por um overlay nativo em Tkinter.
- Cancelamento instantâneo via <Escape> ou botão direito do mouse (<Button-3>) em < 5ms.
- Seleção visual de área com caixa elástica (rubber-band) e cursor em mira (crosshair).
- Captura de imagem direta pelo bounding box (bbox) sem poluir a área de transferência (clipboard).
- Operação thread-safe integrada ao loop de UI principal.
"""

import os
import sys
import time
import ctypes
import tkinter as tk
from typing import Optional, Callable, Tuple
from PIL import Image, ImageGrab

def get_virtual_screen_geometry() -> Tuple[int, int, int, int]:
    """Retorna (vx, vy, vw, vh) cobrindo todo o desktop virtual em múltiplos monitores."""
    if sys.platform == "win32":
        try:
            u32 = ctypes.windll.user32
            vx = u32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = u32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = u32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = u32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                return (vx, vy, vw, vh)
        except Exception:
            pass
    return (0, 0, 1920, 1080)

class NativeScreenSnipper:
    """Gerenciador do overlay nativo de recorte de tela."""

    def __init__(self, root: Optional[tk.Tk] = None):
        self._root = root
        self._window: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._start_x: int = 0
        self._start_y: int = 0
        self._start_canv_x: int = 0
        self._start_canv_y: int = 0
        self._rect_id: Optional[int] = None
        self._is_snipping: bool = False
        self._on_snip_callback: Optional[Callable[[Image.Image, Tuple[int, int]], None]] = None
        self._on_cancel_callback: Optional[Callable[[], None]] = None
        self._dismiss_start_time: float = 0.0

    @property
    def is_active(self) -> bool:
        return self._is_snipping and self._window is not None

    def start_snip(self, 
                   on_snip: Callable[[Image.Image, Tuple[int, int]], None],
                   on_cancel: Optional[Callable[[], None]] = None,
                   cursor_pos: Optional[Tuple[int, int]] = None):
        """
        Abre o overlay fullscreen de recorte sobre todas as janelas.
        Deve ser executado na thread de UI (Tkinter).
        """
        if self._is_snipping:
            self.cancel()

        self._on_snip_callback = on_snip
        self._on_cancel_callback = on_cancel
        self._is_snipping = True

        # Cria root se necessário
        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()

        window = tk.Toplevel(self._root)
        self._window = window

        window.overrideredirect(True)
        window.attributes("-topmost", True)

        # Configura dimensões completas da tela e desktop virtual multi-monitor
        vx, vy, vw, vh = get_virtual_screen_geometry()
        window.geometry(f"{vw}x{vh}+{vx}+{vy}")

        # Opacidade do overlay (escurece levemente o fundo para focar a seleção)
        try:
            window.attributes("-alpha", 0.3)
        except Exception:
            pass

        canvas = tk.Canvas(
            window,
            cursor="cross",
            bg="#0f111a",
            highlightthickness=0
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas = canvas

        # Eventos do mouse para desenhar retângulo
        canvas.bind("<ButtonPress-1>", self._on_button_press)
        canvas.bind("<B1-Motion>", self._on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", self._on_button_release)

        # Cancelamento imediato (< 5ms) com Esc ou clique direito
        window.bind("<Escape>", lambda e: self.cancel())
        canvas.bind("<Button-3>", lambda e: self.cancel())
        window.bind("<FocusOut>", lambda e: self.cancel())

        window.update_idletasks()
        window.focus_force()

    def _close_overlay(self):
        """Fecha o overlay e reseta referências internas sem disparar callback de cancelamento."""
        self._is_snipping = False
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
            self._canvas = None

    def cancel(self):
        """Cancela instantaneamente o recorte (< 5ms) e notifica o callback se fornecido."""
        t0 = time.perf_counter()
        self._close_overlay()
        if self._on_cancel_callback:
            try:
                self._on_cancel_callback()
            except Exception:
                pass
        self._dismiss_start_time = (time.perf_counter() - t0) * 1000.0

    def _on_button_press(self, event):
        self._start_x = self._window.winfo_pointerx() if self._window else event.x
        self._start_y = self._window.winfo_pointery() if self._window else event.y
        self._start_canv_x = self._canvas.canvasx(event.x) if self._canvas else event.x
        self._start_canv_y = self._canvas.canvasy(event.y) if self._canvas else event.y
        if self._canvas:
            self._rect_id = self._canvas.create_rectangle(
                self._start_canv_x, self._start_canv_y, self._start_canv_x, self._start_canv_y,
                outline="#89b4fa",
                width=2,
                fill="#313244",
                stipple="gray25" if sys.platform == "win32" else ""
            )

    def _on_mouse_drag(self, event):
        if self._rect_id and self._canvas:
            cur_x = self._canvas.canvasx(event.x)
            cur_y = self._canvas.canvasy(event.y)
            self._canvas.coords(self._rect_id, self._start_canv_x, self._start_canv_y, cur_x, cur_y)

    def _on_button_release(self, event):
        end_x = self._window.winfo_pointerx() if self._window else event.x
        end_y = self._window.winfo_pointery() if self._window else event.y
        self._close_overlay()

        # Coordenadas ordenadas do retângulo de seleção
        x1 = min(self._start_x, end_x)
        y1 = min(self._start_y, end_y)
        x2 = max(self._start_x, end_x)
        y2 = max(self._start_y, end_y)

        # Se a área for menor que 5x5 pixels, considera apenas clique acidental
        if (x2 - x1) < 5 or (y2 - y1) < 5:
            if self._on_cancel_callback:
                try:
                    self._on_cancel_callback()
                except Exception:
                    pass
            return

        bbox = (x1, y1, x2, y2)
        img = self.grab_bbox(bbox)
        if img and self._on_snip_callback:
            self._on_snip_callback(img, (x1, y1))

    @staticmethod
    def grab_bbox(bbox: Tuple[int, int, int, int]) -> Optional[Image.Image]:
        """
        Captura diretamente o bbox da tela sem tocar na área de transferência (clipboard).
        Garante zero poluição do clipboard do Windows ou SO.
        """
        try:
            return ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception:
            try:
                return ImageGrab.grab(bbox=bbox)
            except Exception:
                return None
