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
from typing import Optional, Callable, Dict, Any

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
VK_T = 0x54
VK_ESCAPE = 0x1B

def _setup_clipboard_prototypes():
    if sys.platform != "win32":
        return
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [ctypes.c_uint]

_setup_clipboard_prototypes()

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

        # Paleta de cores escura (Catppuccin Mocha / Tokyo Night)
        bg_dark = "#181825"
        card_bg = "#1e1e2e"
        border_color = "#313244"
        accent_blue = "#89b4fa"
        accent_green = "#a6e3a1"
        accent_yellow = "#f9e2af"
        text_primary = "#cdd6f4"
        text_secondary = "#a6adc8"
        btn_bg = "#313244"
        btn_hover = "#45475a"

        # Frame principal com borda sutil
        main_frame = tk.Frame(window, bg=card_bg, highlightbackground=border_color, highlightthickness=2, padx=12, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Header (Logo + Engine Badge + Latência + Botão Fechar)
        header_frame = tk.Frame(main_frame, bg=card_bg)
        header_frame.pack(fill=tk.X, pady=(0, 6))

        logo_label = tk.Label(header_frame, text="⚡ LoTra HUD", font=("Segoe UI", 10, "bold"), fg=accent_blue, bg=card_bg)
        logo_label.pack(side=tk.LEFT)

        engine_badge = tk.Label(header_frame, text=f"• {engine_name[:32]}", font=("Segoe UI", 8), fg=text_secondary, bg=card_bg)
        engine_badge.pack(side=tk.LEFT, padx=6)

        latency_badge = tk.Label(header_frame, text=f"⏱ {latency_ms:.1f}ms", font=("Segoe UI", 8, "bold"), fg=accent_green, bg=card_bg)
        latency_badge.pack(side=tk.LEFT, padx=4)

        close_btn = tk.Label(header_frame, text=" ✕ ", font=("Segoe UI", 9, "bold"), fg="#f38ba8", bg=card_bg, cursor="hand2")
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.dismiss())

        # 2. Texto de Origem (se presente e diferente da tradução)
        if source_text and source_text.strip() != translated_text.strip():
            src_display = source_text.strip()
            if len(src_display) > 120:
                src_display = src_display[:117] + "..."
            src_label = tk.Label(main_frame, text=f'"{src_display}"', font=("Segoe UI", 9, "italic"), fg=text_secondary, bg=card_bg, wraplength=420, justify=tk.LEFT)
            src_label.pack(anchor="w", pady=(0, 4))

        # Divisor sutil
        sep = tk.Frame(main_frame, height=1, bg=border_color)
        sep.pack(fill=tk.X, pady=4)

        # 3. Texto Traduzido (Destaque Principal)
        trans_display = translated_text.strip()
        trans_label = tk.Label(
            main_frame,
            text=trans_display,
            font=("Segoe UI", 11, "bold"),
            fg=text_primary,
            bg=card_bg,
            wraplength=440,
            justify=tk.LEFT
        )
        trans_label.pack(anchor="w", pady=(4, 8))

        # 4. Barra de Ações (Copiar, Tecla Esc para fechar)
        actions_frame = tk.Frame(main_frame, bg=card_bg)
        actions_frame.pack(fill=tk.X, pady=(2, 0))

        def copy_action():
            set_windows_clipboard_text(trans_display)
            copy_btn.config(text="✓ Copiado!", fg=accent_green)
            window.after(1200, lambda: copy_btn.config(text="📋 Copiar", fg=text_primary))

        copy_btn = tk.Label(actions_frame, text="📋 Copiar", font=("Segoe UI", 8, "bold"), fg=text_primary, bg=btn_bg, padx=8, pady=3, cursor="hand2")
        copy_btn.pack(side=tk.LEFT)
        copy_btn.bind("<Button-1>", lambda e: copy_action())

        hint_label = tk.Label(actions_frame, text="(Esc ou clique fora fecha)", font=("Segoe UI", 8), fg=text_secondary, bg=card_bg)
        hint_label.pack(side=tk.RIGHT)

        # Binds para fechar com Esc ou clique
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
                self._root.update()
            except Exception:
                pass

class HotkeyListener:
    """Escutador de tecla de atalho nativo para Windows (Win32 RegisterHotKey e GetAsyncKeyState)."""

    def __init__(self, callback: Callable[[], None], hotkey_vk: int = VK_T, modifiers: int = (MOD_CONTROL | MOD_ALT)):
        self.callback = callback
        self.hotkey_vk = hotkey_vk
        self.modifiers = modifiers
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
        HOTKEY_ID = 101

        # Tenta registrar via RegisterHotKey
        registered = user32.RegisterHotKey(0, HOTKEY_ID, self.modifiers, self.hotkey_vk)
        
        if registered:
            msg = ctypes.wintypes.MSG()
            try:
                while self.running:
                    # PeekMessageW sem bloquear indefinidamente
                    if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1): # PM_REMOVE
                        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                            try:
                                self.callback()
                            except Exception as e:
                                print(f"[HotkeyListener Error] {e}")
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.04)
            finally:
                user32.UnregisterHotKey(0, HOTKEY_ID)
        else:
            # Fallback para polling via GetAsyncKeyState (não requer registro exclusivo)
            VK_CONTROL = 0x11
            VK_MENU = 0x12 # ALT
            while self.running:
                ctrl_down = (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
                alt_down = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
                key_down = (user32.GetAsyncKeyState(self.hotkey_vk) & 0x8000) != 0

                if ctrl_down and alt_down and key_down:
                    try:
                        self.callback()
                    except Exception as e:
                        print(f"[Hotkey Polling Error] {e}")
                    # Espera soltar tecla para não disparar em loop contínuo
                    time.sleep(0.4)
                time.sleep(0.05)
