"""
HUD Tooltip e Hotkey Listener do LoTra para Windows:
- Overlay flutuante estilizado (Heads-Up Display) sobreposto a qualquer aplicação ou leitor PDF.
- Suporte estrito a 2 comandos:
    1. [Alt + Q]: Tradução de texto selecionado com simulação automática de cópia (dispensa Ctrl+C prévio).
    2. [Alt + W]: OCR de captura/recorte de tela (Windows Snipping) ou imagem do clipboard.
- Tipografia serifada elegante em Times New Roman.
- Normalização inteligente de quebras de linha duras de PDFs em fluxo contínuo de parágrafos.
- Fechamento com Esc, clique fora, clique no HUD ou timeout configurável.
"""

import os
import sys
import re
import time
import threading
import ctypes
import ctypes.wintypes
from typing import Optional, Callable, Dict, Any, Tuple

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
VK_ESCAPE = 0x1B
VK_Q = 0x51
VK_W = 0x57
VK_C = 0x43
VK_CONTROL = 0x11
VK_MENU = 0x12  # ALT key
KEYEVENTF_KEYUP = 0x0002

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]

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
    u32.keybd_event.restype = None
    u32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_uint, ctypes.c_size_t]
    u32.GetClipboardSequenceNumber.restype = ctypes.c_uint
    u32.GetClipboardSequenceNumber.argtypes = []

    # User32 Multi-Monitor & Foreground Window
    u32.MonitorFromPoint.restype = ctypes.c_void_p
    u32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.c_uint]
    u32.GetMonitorInfoW.restype = ctypes.c_bool
    u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    u32.GetForegroundWindow.argtypes = []
    u32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
    u32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]

    # Shcore DPI per monitor
    try:
        if hasattr(ctypes.windll, "shcore") and hasattr(ctypes.windll.shcore, "GetDpiForMonitor"):
            ctypes.windll.shcore.GetDpiForMonitor.restype = ctypes.c_long
            ctypes.windll.shcore.GetDpiForMonitor.argtypes = [
                ctypes.c_void_p, ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)
            ]
    except Exception:
        pass

enable_dpi_awareness()
_setup_win32_prototypes()

def get_monitor_work_area_for_point(x: int, y: int) -> Tuple[int, int, int, int]:
    """
    Retorna a área de trabalho (rcWork: left, top, right, bottom) do monitor que contém o ponto (x, y).
    Garante suporte a múltiplos monitores com coordenadas virtuais negativas.
    """
    if sys.platform == "win32":
        try:
            pt = ctypes.wintypes.POINT(int(x), int(y))
            MONITOR_DEFAULTTONEAREST = 2
            h_mon = ctypes.windll.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
            if h_mon:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if ctypes.windll.user32.GetMonitorInfoW(h_mon, ctypes.byref(mi)):
                    return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        except Exception:
            pass
    return (0, 0, 1920, 1080)

def get_dpi_for_point(x: int, y: int) -> int:
    """
    Retorna o DPI efetivo do monitor no ponto (x, y) utilizando GetDpiForMonitor,
    GetDpiForSystem ou 96 (padrão 100% de escala) caso não esteja no Windows ou a API falhe.
    """
    if sys.platform == "win32":
        try:
            pt = ctypes.wintypes.POINT(int(x), int(y))
            MONITOR_DEFAULTTONEAREST = 2
            h_mon = ctypes.windll.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
            if h_mon and hasattr(ctypes.windll, "shcore") and hasattr(ctypes.windll.shcore, "GetDpiForMonitor"):
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                # MDT_EFFECTIVE_DPI = 0
                if ctypes.windll.shcore.GetDpiForMonitor(h_mon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                    return int(dpi_x.value)
        except Exception:
            pass
        try:
            if hasattr(ctypes.windll.user32, "GetDpiForSystem"):
                return int(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            pass
    return 96

def is_process_elevated() -> bool:
    """Verifica se o processo atual do LoTra está rodando com privilégios de Administrador."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def is_foreground_window_elevated() -> bool:
    """Verifica se a janela atualmente em primeiro plano pertence a um processo elevado (Admin)."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return False
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h_proc:
            # ERROR_ACCESS_DENIED (5) indica processo protegido/elevado
            return kernel32.GetLastError() == 5
        try:
            TOKEN_QUERY = 0x0008
            h_token = ctypes.wintypes.HANDLE()
            if not advapi32.OpenProcessToken(h_proc, TOKEN_QUERY, ctypes.byref(h_token)):
                return kernel32.GetLastError() == 5
            try:
                class TOKEN_ELEVATION(ctypes.Structure):
                    _fields_ = [("TokenIsElevated", ctypes.wintypes.DWORD)]
                elevation = TOKEN_ELEVATION()
                ret_len = ctypes.wintypes.DWORD()
                if advapi32.GetTokenInformation(h_token, 20, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(ret_len)):
                    return bool(elevation.TokenIsElevated)
            finally:
                kernel32.CloseHandle(h_token)
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return False

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

def normalize_text_spacing(text: str) -> str:
    """
    Normaliza texto extraído de PDFs, navegadores e leitores de documentos:
    - Converte quebras de linha duras de colunas de PDF em fluxo contínuo e fluído.
    - Desfaz hifenizações de final de linha (ex: 'over-\\nreliance' -> 'over-reliance', 'inter-\\noperability' -> 'interoperability').
    - Preserva parágrafos legítimos (linhas separadas por linha em branco onde a anterior termina com pontuação).
    - Preserva itens de listas (bullet points e números), separando-os de forma compacta com newline simples (\\n), sem espaçamentos verticais excessivos.
    - Remove espaços duplicados e evita espaçamentos verticais desnecessários no HUD.
    """
    if not text:
        return ""

    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not t:
        return ""

    # Desfaz hifenização de quebra de linha de PDFs com suporte a caracteres latinos acentuados
    t = re.sub(r'(\b[a-zA-ZÀ-ÿ]+)-\n\s*([a-zà-ÿ][a-zA-ZÀ-ÿ]*)', r'\1\2', t)
    t = re.sub(r'(\b[a-zA-ZÀ-ÿ]+)-\n\s*([A-ZÀ-ß][a-zA-ZÀ-ÿ]*)', r'\1-\2', t)

    # Garante espaço após pontuação final colada em letra (ex: 'hello.World' -> 'hello. World')
    t = re.sub(r'([.?!:;,])([a-zA-ZÀ-ÿ])', r'\1 \2', t)

    raw_lines = [line.strip() for line in t.split("\n")]
    sentence_end = ('.', '!', '?', ':', ';')
    list_marker = re.compile(r'^(\d+[\.\)]|[\u2022\u2023\u25E6\u2043\u2219\*\-\+])\s+')

    paragraphs = []
    current_tokens = []

    for line in raw_lines:
        if not line:
            if current_tokens:
                combined = " ".join(current_tokens).strip()
                if combined:
                    paragraphs.append(combined)
                    current_tokens = []
            continue

        if list_marker.match(line):
            if current_tokens:
                paragraphs.append(" ".join(current_tokens).strip())
                current_tokens = []
            paragraphs.append(line)
        else:
            current_tokens.append(line)

    if current_tokens:
        paragraphs.append(" ".join(current_tokens).strip())

    if not paragraphs:
        return ""

    # Une parágrafos: itens de listas usam quebra simples (\n) para evitar janelas enormes e vazias;
    # blocos de parágrafos normais usam quebra dupla (\n\n).
    out_chunks = []
    for i, p in enumerate(paragraphs):
        if not p:
            continue
        if i == 0:
            out_chunks.append(p)
        else:
            prev = paragraphs[i - 1]
            if list_marker.match(p) or list_marker.match(prev):
                out_chunks.append("\n" + p)
            else:
                out_chunks.append("\n\n" + p)

    result = "".join(out_chunks)
    result = re.sub(r'[ \t]+', ' ', result).strip()
    return result

def simulate_copy_selection(timeout_sec: float = 0.35) -> str:
    """
    Simula o comando de cópia (Ctrl+C) na janela ativa do Windows
    para capturar o texto selecionado pelo usuário sem que seja necessário
    pressionar Ctrl+C manualmente antes de Alt+Q.

    Verificação O(0ms) de integridade de token UIPI:
    Se a janela em primeiro plano for de nível elevado (Administrador) e o LoTra
    estiver em privilégio padrão:
    - Se o usuário já tiver copiado texto manualmente para o clipboard (pre-copied), utiliza-o imediatamente.
    - Se o clipboard estiver vazio, aborta instantaneamente em O(0ms) e retorna aviso explicativo
      sem travar o usuário aguardando timeout de mensagens que o kernel descartaria.
    """
    if sys.platform != "win32":
        return ""

    user32 = ctypes.windll.user32

    # 0. Verificação O(0ms) de integridade UIPI antes de enviar eventos de teclado
    if not is_process_elevated() and is_foreground_window_elevated():
        pre_copied = get_windows_clipboard_text().strip()
        if pre_copied:
            return pre_copied
        return "[Aviso UIPI] Janela em modo Administrador detectada. Execute o LoTra como Administrador ou use Ctrl+C antes do Alt+Q."

    seq_before = user32.GetClipboardSequenceNumber()

    # 1. Garante que as teclas modificadoras estejam liberadas para não interferir no envio do Ctrl+C
    VK_LMENU = 0xA4
    VK_RMENU = 0xA5
    user32.keybd_event(VK_LMENU, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_RMENU, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)

    # 2. Emite o comando Ctrl+C
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.015)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.015)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    # 3. Aguarda a aplicação ativa atualizar o clipboard
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        time.sleep(0.02)
        if user32.GetClipboardSequenceNumber() != seq_before:
            break

    # 4. Retorna o texto capturado ou trata restrição de privilégio UIPI
    if user32.GetClipboardSequenceNumber() == seq_before:
        if not is_process_elevated() and is_foreground_window_elevated():
            pre_copied = get_windows_clipboard_text().strip()
            if pre_copied:
                return pre_copied
            return "[Aviso UIPI] Janela em modo Administrador detectada. Execute o LoTra como Administrador ou use Ctrl+C antes do Alt+Q."
        return ""

    return get_windows_clipboard_text()

class HUDTooltip:
    """
    Gerenciador da janela flutuante overlay (HUD Tooltip) em Tkinter:
    - Tipografia em Times New Roman (conforme solicitado pelo usuário).
    - Paleta cromática teal (#0f5c6e / #0b2329 / #f6f1e8) alinhada com a logo oficial do projeto.
    - Fechamento confiável ao clicar fora da box em qualquer área da tela ou outro aplicativo.
    - Sem auto-dismiss forçado por padrão (timeout_sec=0.0): permanece aberto até o usuário decidir fechar.
    """
    
    def __init__(self):
        self._root = None
        self._window = None
        self._close_timer = None
        self._outside_poll_job = None
        self._is_active = False

    def show(self, 
             translated_text: str, 
             source_text: str = "", 
             latency_ms: float = 0.0, 
             engine_name: str = "LoTra Engine",
             timeout_sec: float = 0.0,
             cursor_pos: Optional[tuple] = None):
        """Exibe o HUD tooltip próximo ao cursor do mouse com layout alinhado à identidade visual."""
        import tkinter as tk

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
        window.attributes("-alpha", 0.97)

        # Paleta de cores condizente com a nova logo da Lontra (Teal e Creme de Meio.dc.html)
        bg_dark = "#0b2329"        # Fundo teal profundo
        border_color = "#166a7d"   # Contorno suave teal
        text_primary = "#f6f1e8"   # Texto creme da logo oficial

        # Frame único minimalista com borda sutil e preenchimento confortável
        main_frame = tk.Frame(window, bg=bg_dark, highlightbackground=border_color, highlightthickness=1, padx=14, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Normaliza o texto traduzido para evitar quebras abruptas e espaços em branco desnecessários
        trans_display = normalize_text_spacing(translated_text)
        trans_display = re.sub(r'\n\s*\n+', '\n\n', trans_display.strip())

        # Obtém posição do cursor com suporte a múltiplos monitores
        if cursor_pos is None and sys.platform == "win32":
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cx, cy = pt.x, pt.y
        elif cursor_pos:
            cx, cy = cursor_pos
        else:
            cx, cy = 400, 300

        # Limites e área de trabalho real do monitor onde o cursor se encontra (suporte multi-monitor)
        mon_left, mon_top, mon_right, mon_bottom = get_monitor_work_area_for_point(cx, cy)
        mon_w = max(400, mon_right - mon_left)

        # Escala dinâmica de DPI por monitor via GetDpiForMonitor
        dpi = get_dpi_for_point(cx, cy)
        dpi_scale = max(1.0, dpi / 96.0)
        font_size = max(9, int(round(11 * dpi_scale)))

        # Ajuste dinâmico de largura de quebra para garantir tipografia e proporções ideais
        char_len = len(trans_display)
        if char_len < 45 and "\n" not in trans_display:
            wrap_width = 0  # Texto curto em linha única
        elif char_len < 160:
            wrap_width = int(440 * dpi_scale)
        elif char_len < 450:
            wrap_width = int(540 * dpi_scale)
        else:
            wrap_width = int(620 * dpi_scale)

        # Não excede a largura utilizável do monitor atual
        max_wrap = max(int(360 * dpi_scale), mon_w - int(80 * dpi_scale))
        if wrap_width > 0:
            wrap_width = min(wrap_width, max_wrap)

        # Texto traduzido com fonte Times New Roman serifada, elegante e compacta escalada por DPI
        trans_label = tk.Label(
            main_frame,
            text=trans_display,
            font=("Times New Roman", font_size),
            fg=text_primary,
            bg=bg_dark,
            wraplength=wrap_width,
            justify=tk.LEFT,
            padx=2,
            pady=2
        )
        trans_label.pack(anchor="w")

        # Clicar em qualquer parte da janela copia a tradução e fecha
        def on_click(event):
            set_windows_clipboard_text(trans_display)
            self.dismiss()

        window.bind("<Button-1>", on_click)
        main_frame.bind("<Button-1>", on_click)
        trans_label.bind("<Button-1>", on_click)

        # Fecha com Esc no Tkinter
        window.bind("<Escape>", lambda e: self.dismiss())

        # Posicionamento inteligente próximo ao cursor ou centralizado
        window.update_idletasks()
        win_w = window.winfo_reqwidth()
        win_h = window.winfo_reqheight()

        pos_x = cx + 15
        pos_y = cy + 18

        # Clamping com suporte total a múltiplos monitores (incluindo coordenadas virtuais negativas)
        min_x = mon_left + 15
        max_x = mon_right - win_w - 15
        min_y = mon_top + 15
        max_y = mon_bottom - win_h - 15

        if pos_x > max_x:
            pos_x = max(min_x, cx - win_w - 15) if (cx - win_w - 15) >= min_x else max_x
        if pos_x < min_x:
            pos_x = min_x

        if pos_y > max_y:
            pos_y = max(min_y, cy - win_h - 10)
        if pos_y < min_y:
            pos_y = min_y

        window.geometry(f"+{pos_x}+{pos_y}")

        # Agendamento de auto-dismiss apenas se explicitamente configurado > 0 (padrão é 0 = sem auto-dismiss)
        if timeout_sec > 0:
            self._close_timer = window.after(int(timeout_sec * 1000), self.dismiss)

        # Inicia monitoramento de clique fora da box (garante fechamento ao clicar em qualquer outro app/desktop)
        if sys.platform == "win32":
            self._outside_poll_job = window.after(180, self._check_click_outside)

    def _check_click_outside(self):
        """Monitora periodicamente se o usuário clicou fora da janela do HUD para fechá-la imediatamente."""
        if not self._is_active or not self._window:
            return

        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            # VK_LBUTTON = 0x01, VK_RBUTTON = 0x02, VK_ESCAPE = 0x1B
            lbutton_down = (user32.GetAsyncKeyState(0x01) & 0x8000) != 0
            rbutton_down = (user32.GetAsyncKeyState(0x02) & 0x8000) != 0
            esc_down = (user32.GetAsyncKeyState(0x1B) & 0x8000) != 0

            if esc_down:
                self.dismiss()
                return

            if lbutton_down or rbutton_down:
                pt = ctypes.wintypes.POINT()
                if user32.GetCursorPos(ctypes.byref(pt)):
                    try:
                        wx = self._window.winfo_rootx()
                        wy = self._window.winfo_rooty()
                        ww = self._window.winfo_width()
                        wh = self._window.winfo_height()
                        # Se o clique ocorreu fora do retângulo do HUD, descarta imediatamente
                        if not (wx <= pt.x <= (wx + ww) and wy <= pt.y <= (wy + wh)):
                            self.dismiss()
                            return
                    except Exception:
                        pass

        if self._is_active and self._window:
            self._outside_poll_job = self._window.after(50, self._check_click_outside)

    def dismiss(self):
        """Fecha o tooltip atual com segurança."""
        self._is_active = False
        if self._window is not None:
            try:
                if self._close_timer:
                    self._window.after_cancel(self._close_timer)
                    self._close_timer = None
                if self._outside_poll_job:
                    self._window.after_cancel(self._outside_poll_job)
                    self._outside_poll_job = None
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
    """
    Escutador de teclas de atalho nativo para Windows:
    Registra estritamente os 2 comandos globais suportados:
    1. [Alt + Q]: Tradução de texto selecionado.
    2. [Alt + W]: OCR de tela / snipping ou imagem.
    (Qualquer atalho redundante anterior, como Ctrl+Alt+T, foi desativado).
    """

    def __init__(self, callback: Callable[[], None], on_ocr_snip: Optional[Callable[[], None]] = None):
        self.callback = callback  # Disparado com Alt+Q (Seleção)
        self.on_ocr_snip = on_ocr_snip  # Disparado com Alt+W (OCR)
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
        HOTKEY_ID_Q = 101
        HOTKEY_ID_W = 102
        VK_Q = 0x51
        VK_W = 0x57
        MOD_NOREPEAT = 0x4000

        # Registra estritamente os 2 atalhos: Alt+Q e Alt+W (com MOD_NOREPEAT para evitar disparos repetidos por retenção da tecla)
        reg_q = user32.RegisterHotKey(0, HOTKEY_ID_Q, MOD_ALT | MOD_NOREPEAT, VK_Q)
        if not reg_q:
            reg_q = user32.RegisterHotKey(0, HOTKEY_ID_Q, MOD_ALT, VK_Q)

        reg_w = user32.RegisterHotKey(0, HOTKEY_ID_W, MOD_ALT | MOD_NOREPEAT, VK_W)
        if not reg_w:
            reg_w = user32.RegisterHotKey(0, HOTKEY_ID_W, MOD_ALT, VK_W)

        if reg_q or reg_w:
            msg = ctypes.wintypes.MSG()
            try:
                while self.running:
                    # Drena mensagens pendentes sem bloquear indefinidamente
                    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE
                        if msg.message == WM_HOTKEY:
                            if msg.wParam == HOTKEY_ID_Q and self.callback:
                                try:
                                    self.callback()
                                except Exception as e:
                                    print(f"[HotkeyListener Alt+Q Error] {e}")
                            elif msg.wParam == HOTKEY_ID_W and self.on_ocr_snip:
                                try:
                                    self.on_ocr_snip()
                                except Exception as e:
                                    print(f"[HotkeyListener Alt+W Error] {e}")
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.03)
            finally:
                if reg_q:
                    user32.UnregisterHotKey(0, HOTKEY_ID_Q)
                if reg_w:
                    user32.UnregisterHotKey(0, HOTKEY_ID_W)
        else:
            # Fallback para polling via GetAsyncKeyState (não requer registro exclusivo)
            VK_MENU = 0x12  # ALT
            while self.running:
                alt_down = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
                q_down = (user32.GetAsyncKeyState(VK_Q) & 0x8000) != 0
                w_down = (user32.GetAsyncKeyState(VK_W) & 0x8000) != 0

                # Dispara se [Alt + Q] for pressionado
                if alt_down and q_down:
                    if self.callback:
                        try:
                            self.callback()
                        except Exception as e:
                            print(f"[Hotkey Polling Alt+Q Error] {e}")
                    time.sleep(0.4)
                # Dispara se [Alt + W] for pressionado
                elif alt_down and w_down and self.on_ocr_snip:
                    try:
                        self.on_ocr_snip()
                    except Exception as e:
                        print(f"[Hotkey Polling Alt+W Error] {e}")
                    time.sleep(0.4)
                time.sleep(0.05)
