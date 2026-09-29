"""
HUD Tooltip e Hotkey Listener do LoTra para Windows:
- Overlay flutuante estilizado (Heads-Up Display) sobreposto a qualquer aplicação ou leitor PDF.
- Escuta de atalho global do Windows (Ctrl+Alt+T) via Win32 RegisterHotKey ou polling GetAsyncKeyState.
- Captura de texto/imagem da área de transferência ou seleção ativa.
- Exibição de texto original, tradução, tempo de latência e motor selecionado.
- Fechamento com Esc, clique fora, botão de fechar ou timeout configurável.
"""

import os
import sys
import time
import threading
import ctypes
import ctypes.wintypes
from typing import Optional, Callable, Dict, Any

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
VK_T = 0x54
VK_ESCAPE = 0x1B

def enable_dpi_awareness():
    """Habilita conscientização de DPI por monitor no Windows para evitar distorção e coordenadas erradas."""
    if sys.platform != "win32":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE (2)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

def _setup_win32_prototypes():
    if sys.platform != "win32":
        return
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32

    # Kernel32 Memory
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.restype = ctypes.c_bool
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalFree.restype = ctypes.c_void_p
    k32.GlobalFree.argtypes = [ctypes.c_void_p]

    # User32 Clipboard
    u32.OpenClipboard.restype = ctypes.c_bool
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    u32.CloseClipboard.restype = ctypes.c_bool
    u32.CloseClipboard.argtypes = []
    u32.EmptyClipboard.restype = ctypes.c_bool
    u32.EmptyClipboard.argtypes = []
    u32.SetClipboardData.restype = ctypes.c_void_p
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [ctypes.c_uint]

    # User32 Hotkeys & Cursor
    u32.RegisterHotKey.restype = ctypes.c_bool
    u32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    u32.UnregisterHotKey.restype = ctypes.c_bool
    u32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u32.PeekMessageW.restype = ctypes.c_bool
    u32.PeekMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    u32.TranslateMessage.restype = ctypes.c_bool
    u32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
    u32.DispatchMessageW.restype = ctypes.c_long
    u32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
    u32.GetAsyncKeyState.restype = ctypes.c_short
    u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    u32.GetCursorPos.restype = ctypes.c_bool
    u32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]

enable_dpi_awareness()
_setup_win32_prototypes()

def get_windows_clipboard_text() -> str:
    """Lê texto da área de transferência do Windows via Win32 API direta."""
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    
    # Tenta abrir o clipboard com breves tentativas se estiver ocupado
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return ""

    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

def set_windows_clipboard_text(text: str) -> bool:
    """Grava texto na área de transferência do Windows via Win32 API."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    
    encoded = (text + "\0").encode("utf-16le")
    size = len(encoded)
    
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not h_mem:
        return False
        
    ptr = kernel32.GlobalLock(h_mem)
    if not ptr:
        kernel32.GlobalFree(h_mem)
        return False
        
    ctypes.memmove(ptr, encoded, size)
    kernel32.GlobalUnlock(h_mem)
    
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        kernel32.GlobalFree(h_mem)
        return False
        
    try:
        user32.EmptyClipboard()
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return bool(res)
    finally:
        user32.CloseClipboard()

class HUDTooltip:
    """Gerenciador da janela flutuante overlay (HUD Tooltip) em Tkinter."""
    
    def __init__(self):
        self._root = None
        self._window = None
        self._close_timer = None
        self._is_active = False

    def show(self, 
             translated_text: str, 
             source_text: str = "", 
             latency_ms: float = 0.0, 
             engine_name: str = "LoTra Engine",
             timeout_sec: float = 7.0,
             cursor_pos: Optional[tuple] = None):
        """Exibe o HUD tooltip próximo ao cursor do mouse com layout moderno escuro."""
        import tkinter as tk
        from tkinter import ttk

        # Se já existir uma janela aberta, fecha antes de abrir a nova
        self.dismiss()

        # Cria a janela raiz se necessário
        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()

        window = tk.Toplevel(self._root)
        self._window = window
        self._is_active = True

        # Janela de sobreposição (topmost e sem bordas do sistema)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.96) # Leve translucidez moderna

        # Paleta de cores minimalista escura
        bg_dark = "#181825"
        border_color = "#313244"
        text_primary = "#cdd6f4"

        # Frame único minimalista com borda sutil e preenchimento confortável
        main_frame = tk.Frame(window, bg=bg_dark, highlightbackground=border_color, highlightthickness=1, padx=12, pady=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        trans_display = translated_text.strip()
        # Se for texto curto (palavra ou frase pequena), mantém linha única compacta; se for longo, quebra em 420px
        wrap_width = 420 if len(trans_display) > 40 else 0

        # Único elemento: Texto traduzido limpo, sem ícones, cabeçalhos ou dados adicionais
        trans_label = tk.Label(
            main_frame,
            text=trans_display,
            font=("Segoe UI", 10),
            fg=text_primary,
            bg=bg_dark,
            wraplength=wrap_width,
            justify=tk.LEFT
        )
        trans_label.pack(anchor="w")

        # Clicar em qualquer parte da janela copia a tradução e fecha
        def on_click(event):
            set_windows_clipboard_text(trans_display)
            self.dismiss()

        window.bind("<Button-1>", on_click)
        main_frame.bind("<Button-1>", on_click)
        trans_label.bind("<Button-1>", on_click)

        # Fecha imediatamente com Esc ou ao clicar fora (perda de foco)
        window.bind("<Escape>", lambda e: self.dismiss())
        window.bind("<FocusOut>", lambda e: self.dismiss())

        # Posicionamento inteligente próximo ao cursor ou centralizado
        window.update_idletasks()
        win_w = window.winfo_reqwidth()
        win_h = window.winfo_reqheight()

        if cursor_pos is None and sys.platform == "win32":
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cx, cy = pt.x, pt.y
        elif cursor_pos:
            cx, cy = cursor_pos
        else:
            cx, cy = 400, 300

        # Posiciona 15px abaixo e 15px à direita do ponteiro do mouse
        pos_x = cx + 15
        pos_y = cy + 18

        # Limites da tela
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()

        if pos_x + win_w > screen_w - 20:
            pos_x = max(20, screen_w - win_w - 20)
        if pos_y + win_h > screen_h - 40:
            pos_y = max(20, cy - win_h - 10)

        window.geometry(f"+{pos_x}+{pos_y}")

        # Agendamento de auto-dismiss
        if timeout_sec > 0:
            self._close_timer = window.after(int(timeout_sec * 1000), self.dismiss)

    def dismiss(self):
        """Fecha o tooltip atual com segurança."""
        self._is_active = False
        if self._window is not None:
            try:
                if self._close_timer:
                    self._window.after_cancel(self._close_timer)
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    def pump_events(self):
        """Processa eventos pendentes da interface Tkinter se houver loop manual."""
        if self._root:
            try:
                self._root.update_idletasks()
                self._root.update()
            except Exception:
                pass

    def destroy(self):
        """Descarta completamente a janela e o contexto do Tkinter."""
        self.dismiss()
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

class HotkeyListener:
    """Escutador de tecla de atalho nativo para Windows (Win32 RegisterHotKey e GetAsyncKeyState)."""

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia escuta em segundo plano."""
        if self.running or sys.platform != "win32":
            return
        self.running = True
        self._thread = threading.Thread(target=self._hotkey_loop, daemon=True, name="LoTra_HotkeyListener")
        self._thread.start()

    def stop(self):
        """Para a escuta de hotkey."""
        self.running = False

    def _hotkey_loop(self):
        user32 = ctypes.windll.user32
        HOTKEY_ID_T = 101
        HOTKEY_ID_Q = 102
        VK_Q = 0x51
        VK_T = 0x54

        # Registra ambos os atalhos: Ctrl+Alt+T e Alt+Q
        reg_t = user32.RegisterHotKey(0, HOTKEY_ID_T, (MOD_CONTROL | MOD_ALT), VK_T)
        reg_q = user32.RegisterHotKey(0, HOTKEY_ID_Q, MOD_ALT, VK_Q)

        if reg_t or reg_q:
            msg = ctypes.wintypes.MSG()
            try:
                while self.running:
                    # PeekMessageW sem bloquear indefinidamente
                    if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1): # PM_REMOVE
                        if msg.message == WM_HOTKEY and msg.wParam in (HOTKEY_ID_T, HOTKEY_ID_Q):
                            try:
                                self.callback()
                            except Exception as e:
                                print(f"[HotkeyListener Error] {e}")
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.04)
            finally:
                if reg_t:
                    user32.UnregisterHotKey(0, HOTKEY_ID_T)
                if reg_q:
                    user32.UnregisterHotKey(0, HOTKEY_ID_Q)
        else:
            # Fallback para polling via GetAsyncKeyState (não requer registro exclusivo)
            VK_CONTROL = 0x11
            VK_MENU = 0x12 # ALT
            while self.running:
                ctrl_down = (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
                alt_down = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
                t_down = (user32.GetAsyncKeyState(VK_T) & 0x8000) != 0
                q_down = (user32.GetAsyncKeyState(VK_Q) & 0x8000) != 0

                # Dispara se [Alt + Q] OU [Ctrl + Alt + T] forem pressionados
                if (alt_down and q_down) or (ctrl_down and alt_down and t_down):
                    try:
                        self.callback()
                    except Exception as e:
                        print(f"[Hotkey Polling Error] {e}")
                    # Espera soltar tecla para não disparar em loop contínuo
                    time.sleep(0.4)
                time.sleep(0.05)
