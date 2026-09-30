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

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("_u", _INPUT_UNION),
    ]

class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("hwndActive", ctypes.c_void_p),
        ("hwndFocus", ctypes.c_void_p),
        ("hwndCapture", ctypes.c_void_p),
        ("hwndMenuOwner", ctypes.c_void_p),
        ("hwndMoveSize", ctypes.c_void_p),
        ("hwndCaret", ctypes.c_void_p),
        ("rcCaret", RECT),
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

    # Kernel32 Memory & Process
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
    u32.GetClipboardSequenceNumber.restype = ctypes.c_uint
    u32.GetClipboardSequenceNumber.argtypes = []

    # User32 Input & Hotkeys
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
    u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_size_t]
    u32.MapVirtualKeyW.restype = ctypes.c_uint
    u32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
    u32.SendInput.restype = ctypes.c_uint
    u32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]

    # User32 Windows & Thread Info
    u32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    u32.GetForegroundWindow.argtypes = []
    u32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
    u32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
    u32.GetGUIThreadInfo.restype = ctypes.c_bool
    u32.GetGUIThreadInfo.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
    u32.SendMessageTimeoutW.restype = ctypes.c_long
    u32.SendMessageTimeoutW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)
    ]

    # User32 Multi-Monitor
    u32.MonitorFromPoint.restype = ctypes.c_void_p
    u32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.c_uint]
    u32.GetMonitorInfoW.restype = ctypes.c_bool
    u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

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

_CLIPBOARD_FALLBACK_BUFFER: str = ""
_last_clipboard_change_time: float = 0.0
_last_clipboard_seq: int = 0
_COPY_SIMULATION_LOCK = threading.Lock()

def _send_synthetic_key(vk: int, is_up: bool = False):
    """Envia evento de tecla usando SendInput com fallback transparente para keybd_event."""
    if sys.platform != "win32":
        return
    u32 = ctypes.windll.user32
    scan = u32.MapVirtualKeyW(vk, 0)
    flags = 0x0002 if is_up else 0

    # 1. Tenta SendInput
    try:
        inp = INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.wScan = scan
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        inp.ki.dwExtraInfo = 0
        arr = (INPUT * 1)(inp)
        if u32.SendInput(1, arr, ctypes.sizeof(INPUT)) == 1:
            return
    except Exception:
        pass

    # 2. Fallback resiliente para keybd_event
    try:
        u32.keybd_event(vk & 0xFF, scan & 0xFF, flags, 0)
    except Exception:
        pass

def _force_release_all_modifiers():
    """Libera todas as teclas modificadoras (Alt, Ctrl, Shift, Win) e a tecla Q sinteticamente."""
    if sys.platform != "win32":
        return
    # Libera Alt
    _send_synthetic_key(0xA4, is_up=True)  # VK_LMENU
    _send_synthetic_key(0xA5, is_up=True)  # VK_RMENU
    _send_synthetic_key(0x12, is_up=True)  # VK_MENU
    # Libera Q
    _send_synthetic_key(0x51, is_up=True)  # VK_Q
    # Libera Shift
    _send_synthetic_key(0xA0, is_up=True)  # VK_LSHIFT
    _send_synthetic_key(0xA1, is_up=True)  # VK_RSHIFT
    _send_synthetic_key(0x10, is_up=True)  # VK_SHIFT
    # Libera Win
    _send_synthetic_key(0x5B, is_up=True)  # VK_LWIN
    _send_synthetic_key(0x5C, is_up=True)  # VK_RWIN

def _suppress_menu_activation():
    """Envia menu-mask key (VK_CONTROL) para evitar que o Windows ative a barra de menu ao soltar Alt."""
    if sys.platform != "win32":
        return
    _send_synthetic_key(0x11, is_up=False)  # Ctrl down
    time.sleep(0.005)
    _send_synthetic_key(0x11, is_up=True)   # Ctrl up

def get_windows_clipboard_text() -> str:
    """Lê texto da área de transferência do Windows via Win32 API direta, com retentativas de lock."""
    global _CLIPBOARD_FALLBACK_BUFFER, _last_clipboard_change_time, _last_clipboard_seq
    if sys.platform != "win32":
        return _CLIPBOARD_FALLBACK_BUFFER

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13

    # Tenta abrir o clipboard com breves tentativas se estiver ocupado
    opened = False
    for _ in range(3):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.005)

    if not opened:
        return _CLIPBOARD_FALLBACK_BUFFER

    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            val = ctypes.c_wchar_p(ptr).value or ""
            if val:
                _CLIPBOARD_FALLBACK_BUFFER = val
                _last_clipboard_change_time = time.time()
            return val
        finally:
            kernel32.GlobalUnlock(handle)
    except Exception:
        return _CLIPBOARD_FALLBACK_BUFFER
    finally:
        user32.CloseClipboard()

def set_windows_clipboard_text(text: str) -> bool:
    """Grava texto na área de transferência do Windows via Win32 API com liberação estrita de recursos."""
    global _CLIPBOARD_FALLBACK_BUFFER, _last_clipboard_change_time, _last_clipboard_seq
    _CLIPBOARD_FALLBACK_BUFFER = text
    _last_clipboard_change_time = time.time()
    if sys.platform != "win32":
        return True

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    encoded = (text + "\0").encode("utf-16le", errors="replace")
    size = len(encoded)

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not h_mem:
        return True

    ptr = kernel32.GlobalLock(h_mem)
    if not ptr:
        kernel32.GlobalFree(h_mem)
        return True

    ctypes.memmove(ptr, encoded, size)
    kernel32.GlobalUnlock(h_mem)

    for _ in range(3):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.005)
    else:
        kernel32.GlobalFree(h_mem)
        return True

    try:
        user32.EmptyClipboard()
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        if not res:
            kernel32.GlobalFree(h_mem)
            return True
        _last_clipboard_seq = user32.GetClipboardSequenceNumber()
        return True
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

    # Sanitiza caracteres nulos, controle e surrogates quebrados
    t = text.replace("\x00", "")
    try:
        t = t.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
    except Exception:
        pass
    t = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]', '', t)

    # Normaliza espaços especiais, caracteres invisíveis e zero-width (Web / PDF / OCR)
    t = t.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ").replace("\xad", "")
    # Preserva ZWJ (\u200d) quando faz parte de sequências compostas de emojis (incluindo cadeias com múltiplos ZWJs)
    emoji_zwj_pat = re.compile(
        r'([\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff](?:[\ufe0e\ufe0f]|[\U0001f3fb-\U0001f3ff])*)\u200d'
        r'([\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff])'
    )
    while True:
        new_t = emoji_zwj_pat.sub(r'\1__LOTRA_EMOJI_ZWJ__\2', t)
        if new_t == t:
            break
        t = new_t
    t = re.sub(r'[\u200b-\u200d\ufeff]', '', t)
    t = t.replace('__LOTRA_EMOJI_ZWJ__', '\u200d')

    t = t.replace("\r\n", "\n").replace("\r", "\n").strip()
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

def simulate_copy_selection(timeout_sec: float = 0.40) -> str:
    """
    Simula o comando de cópia (Ctrl+C) na janela ativa do Windows
    para capturar o texto selecionado pelo usuário sem que seja necessário
    pressionar Ctrl+C manualmente antes de Alt+Q.

    Estratégia ultra-robusta de 8 etapas:
    1. Lock de concorrência com timeout para evitar colisão entre múltiplos disparos rápidos.
    2. Verificação O(0ms) de integridade UIPI: se janela for Admin e LoTra não for,
       usa pré-cópia se existir ou exibe aviso explicativo.
    3. Aguarda liberação física de Alt e Q (até 350ms), retornando imediatamente no release.
    4. Força liberação de todos os modificadores e aplica menu-mask key para impedir Menu Loop.
    5. Captura seq_before via GetClipboardSequenceNumber().
    6. Emite Ctrl+C sintético com scan codes de hardware e hold time calibrado (20ms).
    7. Aguarda de forma reativa a atualização do clipboard (até timeout_sec).
    8. Se sequence number mudou, lê da área de transferência com retentativas de lock.
       Se não mudou, tenta estratégia secundária via WM_COPY na janela com foco.
       Se ainda não mudou, verifica se o usuário pré-copiou manualmente nos últimos 3 segundos.
       Se nada foi selecionado/copiado, retorna string vazia para exibir aviso claro no HUD.
    """
    if sys.platform != "win32":
        return ""

    global _last_clipboard_seq, _last_clipboard_change_time
    user32 = ctypes.windll.user32

    # 1. Lock de concorrência: se outro worker já estiver simulando cópia, aguarda até 0.45s
    acquired = _COPY_SIMULATION_LOCK.acquire(timeout=0.45)
    if not acquired:
        return ""

    try:
        # 2. Verificação O(0ms) de integridade UIPI
        if not is_process_elevated() and is_foreground_window_elevated():
            pre_copied = get_windows_clipboard_text().strip()
            if pre_copied:
                return pre_copied
            return "[Aviso UIPI] Janela em modo Administrador detectada. Execute o LoTra como Administrador ou use Ctrl+C antes do Alt+Q."

        # 3. Aguarda liberação física das teclas Alt e Q (até 350ms)
        deadline_release = time.perf_counter() + 0.35
        while time.perf_counter() < deadline_release:
            alt_pressed = bool(user32.GetAsyncKeyState(0x12) & 0x8000)
            q_pressed = bool(user32.GetAsyncKeyState(0x51) & 0x8000)
            if not alt_pressed and not q_pressed:
                break
            time.sleep(0.015)

        # 4. Libera modificadores e mascara menu para manter o foco no documento
        _force_release_all_modifiers()
        _suppress_menu_activation()
        time.sleep(0.015)

        seq_before = user32.GetClipboardSequenceNumber()

        # 5. Emite Ctrl+C com dual-engine e hold time calibrado
        _send_synthetic_key(0x11, is_up=False)  # Ctrl down
        time.sleep(0.015)
        _send_synthetic_key(0x43, is_up=False)  # C down
        time.sleep(0.025)
        _send_synthetic_key(0x43, is_up=True)   # C up
        time.sleep(0.015)
        _send_synthetic_key(0x11, is_up=True)   # Ctrl up

        # 6. Aguarda a aplicação ativa atualizar o clipboard
        deadline = time.perf_counter() + max(0.25, timeout_sec)
        while time.perf_counter() < deadline:
            time.sleep(0.015)
            if user32.GetClipboardSequenceNumber() != seq_before:
                break

        # 7. Se o número de sequência mudou, lê com breves retentativas
        curr_seq = user32.GetClipboardSequenceNumber()
        if curr_seq != seq_before:
            for _ in range(5):
                clip = get_windows_clipboard_text()
                if clip:
                    _last_clipboard_seq = curr_seq
                    _last_clipboard_change_time = time.time()
                    return clip
                time.sleep(0.02)

        # 8. Estratégia Secundária: Envia WM_COPY (0x0301) diretamente à janela com foco
        try:
            fg = user32.GetForegroundWindow()
            if fg:
                tid = user32.GetWindowThreadProcessId(fg, None)
                gti = GUITHREADINFO()
                gti.cbSize = ctypes.sizeof(GUITHREADINFO)
                if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
                    res_val = ctypes.c_size_t(0)
                    user32.SendMessageTimeoutW(gti.hwndFocus, 0x0301, 0, 0, 2, 100, ctypes.byref(res_val))
                    time.sleep(0.05)
                    if user32.GetClipboardSequenceNumber() != seq_before:
                        for _ in range(4):
                            clip = get_windows_clipboard_text()
                            if clip:
                                _last_clipboard_seq = user32.GetClipboardSequenceNumber()
                                _last_clipboard_change_time = time.time()
                                return clip
                            time.sleep(0.02)
        except Exception:
            pass

        # 9. Fallback seguro para pré-cópia recente do usuário (copiado nos últimos 3 segundos)
        now_ts = time.time()
        if (now_ts - _last_clipboard_change_time) < 3.0:
            existing = get_windows_clipboard_text()
            if existing and existing.strip():
                return existing

        # Se nada foi selecionado ou copiado, retorna vazio para acionar o aviso explicativo do HUD
        return ""
    finally:
        _COPY_SIMULATION_LOCK.release()

class HUDTooltip:
    """
    Gerenciador da janela flutuante overlay (HUD Tooltip) em Tkinter:
    - Tipografia em Times New Roman (conforme solicitado pelo usuário).
    - Paleta cromática teal (#0f5c6e / #0b2329 / #f6f1e8) alinhada com a logo oficial do projeto.
    - Fechamento confiável ao clicar fora da box em qualquer área da tela ou outro aplicativo.
    - Sem auto-dismiss forçado por padrão (timeout_sec=0.0): permanece aberto até o usuário decidir fechar.
    """
    
    def __init__(self, root: Optional[Any] = None):
        self._root = root
        self._window = None
        self._main_frame = None
        self._trans_label = None
        self._close_timer = None
        self._outside_poll_job = None
        self._is_active = False
        self._is_streaming = False
        self._current_text = ""
        self._cursor_pos = (400, 300)
        self._dpi_scale = 1.0
        self._mon_left = 0
        self._mon_top = 0
        self._mon_right = 1920
        self._mon_bottom = 1080
        self._font_size = 11

    def set_root(self, root: Any):
        """Define ou atualiza a raiz única do Tkinter para compartilhamento seguro de event loop."""
        self._root = root

    def _update_geometry(self, display_text: str):
        """Ajusta dimensões, wrap e posição da janela HUD dinamicamente respeitando limites do monitor."""
        if not self._window or not self._trans_label:
            return

        self._full_text = display_text
        char_len = len(display_text)
        mon_w = max(400, self._mon_right - self._mon_left)
        mon_h = max(300, self._mon_bottom - self._mon_top)

        if char_len < 45 and "\n" not in display_text:
            wrap_width = 0
        elif char_len < 160:
            wrap_width = int(440 * self._dpi_scale)
        elif char_len < 450:
            wrap_width = int(540 * self._dpi_scale)
        else:
            wrap_width = int(620 * self._dpi_scale)

        max_wrap = max(int(360 * self._dpi_scale), mon_w - int(80 * self._dpi_scale))
        if wrap_width > 0:
            wrap_width = min(wrap_width, max_wrap)

        # Trunca para visualização limpa no HUD caso o texto selecionado seja gigantesco (> 3500 caracteres)
        if len(display_text) > 3500:
            visual_text = display_text[:3500].rstrip() + "\n\n[... Tradução truncada para exibição no HUD. Clique para copiar o texto completo ...]"
        else:
            visual_text = display_text

        self._trans_label.config(text=visual_text, wraplength=wrap_width)
        self._window.update_idletasks()

        win_w = self._window.winfo_reqwidth()
        win_h = self._window.winfo_reqheight()
        cx, cy = self._cursor_pos

        pos_x = cx + 15
        pos_y = cy + 18

        min_x = self._mon_left + 15
        max_x = max(min_x, self._mon_right - win_w - 15)
        min_y = self._mon_top + 15
        max_y = max(min_y, self._mon_bottom - win_h - 15)

        if pos_x > max_x:
            pos_x = max(min_x, cx - win_w - 15) if (cx - win_w - 15) >= min_x else max_x
        if pos_x < min_x:
            pos_x = min_x

        if pos_y > max_y:
            pos_y = max(min_y, cy - win_h - 10)
        if pos_y < min_y:
            pos_y = min_y

        self._window.geometry(f"+{pos_x}+{pos_y}")

    def start_stream(self, cursor_pos: Optional[tuple] = None):
        """Inicia overlay flutuante imediatamente para streaming em tempo real com TTFT ultra-baixo."""
        import tkinter as tk

        self.dismiss()

        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()

        window = tk.Toplevel(self._root)
        self._window = window
        self._is_active = True
        self._is_streaming = True
        self._current_text = "..."

        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.97)

        bg_dark = "#0b2329"
        border_color = "#166a7d"
        text_primary = "#f6f1e8"

        self._main_frame = tk.Frame(window, bg=bg_dark, highlightbackground=border_color, highlightthickness=1, padx=14, pady=10)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        if cursor_pos is None and sys.platform == "win32":
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cx, cy = pt.x, pt.y
        elif cursor_pos:
            cx, cy = cursor_pos
        else:
            cx, cy = 400, 300

        self._cursor_pos = (cx, cy)
        self._mon_left, self._mon_top, self._mon_right, self._mon_bottom = get_monitor_work_area_for_point(cx, cy)
        dpi = get_dpi_for_point(cx, cy)
        self._dpi_scale = max(1.0, dpi / 96.0)
        self._font_size = max(9, int(round(11 * self._dpi_scale)))

        # Header bar estilizada com badges tipo web card
        self._header_frame = tk.Frame(self._main_frame, bg=bg_dark)
        self._header_frame.pack(fill=tk.X, pady=(0, 6))

        # Brand badge pill
        self._brand_pill = tk.Label(
            self._header_frame,
            text=" LoTra HUD ",
            font=("Arial", max(7, int(8 * self._dpi_scale)), "bold"),
            bg="#0f5c6e",
            fg="#ffffff",
            padx=5,
            pady=1
        )
        self._brand_pill.pack(side=tk.LEFT)

        # Status dot e indicador de motor
        self._status_pill = tk.Label(
            self._header_frame,
            text=" ● Traduzindo... ",
            font=("Arial", max(7, int(8 * self._dpi_scale))),
            bg="#133842",
            fg="#f59e0b",
            padx=5,
            pady=1
        )
        self._status_pill.pack(side=tk.LEFT, padx=(6, 0))

        # Botão Fechar [Esc]
        self._btn_close = tk.Label(
            self._header_frame,
            text=" ✕ Esc ",
            font=("Arial", max(7, int(8 * self._dpi_scale))),
            bg="#18343b",
            fg="#9fb8bd",
            cursor="hand2",
            padx=5,
            pady=1
        )
        self._btn_close.pack(side=tk.RIGHT)

        # Botão Copiar rápido
        self._btn_copy = tk.Label(
            self._header_frame,
            text=" 📋 Copiar ",
            font=("Arial", max(7, int(8 * self._dpi_scale)), "bold"),
            bg="#174e5c",
            fg="#d8eff5",
            cursor="hand2",
            padx=6,
            pady=1
        )
        self._btn_copy.pack(side=tk.RIGHT, padx=(0, 6))

        def on_copy_action(event=None):
            target_copy = getattr(self, "_full_text", "") or self._current_text
            if target_copy and target_copy != "...":
                set_windows_clipboard_text(target_copy)
                try:
                    if hasattr(self, "_btn_copy") and self._btn_copy:
                        self._btn_copy.config(text=" ✓ Copiado! ", bg="#1b8a5a", fg="#ffffff")
                    if hasattr(self, "_footer_lbl") and self._footer_lbl:
                        self._footer_lbl.config(text="✓ Copiado para o clipboard!", fg="#4ade80")
                    if self._window:
                        self._window.after(650, self.dismiss)
                except Exception:
                    self.dismiss()

        self._btn_copy.bind("<Button-1>", on_copy_action)
        self._btn_close.bind("<Button-1>", lambda e: self.dismiss())

        # Rótulo de texto primário (mantém Times New Roman e contrato da suíte)
        self._trans_label = tk.Label(
            self._main_frame,
            text=self._current_text,
            font=("Times New Roman", self._font_size),
            fg=text_primary,
            bg=bg_dark,
            wraplength=int(320 * self._dpi_scale),
            justify=tk.LEFT,
            padx=2,
            pady=2
        )
        self._trans_label.pack(anchor="w")

        # Footer sutil com dica de atalhos e feedback
        self._footer_frame = tk.Frame(self._main_frame, bg=bg_dark)
        self._footer_frame.pack(fill=tk.X, pady=(6, 0))

        self._footer_lbl = tk.Label(
            self._footer_frame,
            text="Clique no card ou no botão para copiar  •  Pressione Esc para fechar",
            font=("Arial", max(7, int(7.5 * self._dpi_scale))),
            fg="#5c8089",
            bg=bg_dark
        )
        self._footer_lbl.pack(anchor="w")

        def on_card_click(event):
            target_copy = getattr(self, "_full_text", "") or self._current_text
            if target_copy and target_copy != "...":
                set_windows_clipboard_text(target_copy)
            self.dismiss()

        window.bind("<Button-1>", on_card_click)
        self._main_frame.bind("<Button-1>", on_card_click)
        self._trans_label.bind("<Button-1>", on_card_click)
        self._footer_frame.bind("<Button-1>", on_card_click)
        self._footer_lbl.bind("<Button-1>", on_card_click)
        window.bind("<Escape>", lambda e: self.dismiss())

        self._update_geometry(self._current_text)

        # Rastreia se o botão do mouse já estava pressionado para evitar fechamento acidental ao soltar
        self._mouse_released_once = False
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                lbutton_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
                self._mouse_released_once = not lbutton_down
            except Exception:
                self._mouse_released_once = True
            self._outside_poll_job = window.after(180, self._check_click_outside)

    def update_stream(self, token_chunk: str, full_text_so_far: str):
        """Atualiza dinamicamente o texto do HUD conforme novos tokens chegam via streaming."""
        if not self._is_active or not self._window or not self._trans_label:
            return

        clean_text = normalize_text_spacing(full_text_so_far)
        clean_text = re.sub(r'\n\s*\n+', '\n\n', clean_text.strip())
        if not clean_text:
            return

        self._current_text = clean_text
        self._update_geometry(clean_text)

    def finish_stream(self, final_text: str, latency_ms: float = 0.0, engine_name: str = ""):
        """Finaliza a sessão de streaming fixando o texto limpo final e reconfigurando clipboard."""
        if not self._is_active or not self._window or not self._trans_label:
            return

        self._is_streaming = False
        clean_text = normalize_text_spacing(final_text) if final_text else self._current_text
        clean_text = re.sub(r'\n\s*\n+', '\n\n', clean_text.strip())
        if not clean_text:
            clean_text = self._current_text

        self._current_text = clean_text
        self._full_text = clean_text
        self._update_geometry(clean_text)

        # Atualiza badge de status para verde quando concluído
        if hasattr(self, "_status_pill") and self._status_pill:
            try:
                eng = engine_name if engine_name else "Pronto"
                if len(eng) > 24:
                    eng = eng[:22] + ".."
                lat_str = f"({latency_ms:.0f}ms)" if latency_ms > 0 else ""
                self._status_pill.config(text=f" ● {eng} {lat_str}".strip() + " ", fg="#4ade80", bg="#133842")
            except Exception:
                pass

        def on_click(event):
            target_copy = getattr(self, "_full_text", "") or clean_text
            if target_copy and target_copy != "...":
                set_windows_clipboard_text(target_copy)
            self.dismiss()

        for w in [self._window, self._main_frame, self._trans_label,
                  getattr(self, "_header_frame", None), getattr(self, "_brand_pill", None),
                  getattr(self, "_status_pill", None), getattr(self, "_footer_frame", None),
                  getattr(self, "_footer_lbl", None)]:
            if w:
                try:
                    w.bind("<Button-1>", on_click)
                except Exception:
                    pass

    def show(self, 
             translated_text: str, 
             source_text: str = "", 
             latency_ms: float = 0.0, 
             engine_name: str = "LoTra Engine",
             timeout_sec: float = 0.0,
             cursor_pos: Optional[tuple] = None):
        """Exibe o HUD tooltip próximo ao cursor do mouse com layout alinhado à identidade visual."""
        self.start_stream(cursor_pos=cursor_pos)
        self.finish_stream(translated_text, latency_ms=latency_ms, engine_name=engine_name)
        if timeout_sec > 0 and self._window:
            self._close_timer = self._window.after(int(timeout_sec * 1000), self.dismiss)

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

            if not getattr(self, "_mouse_released_once", True):
                if not lbutton_down and not rbutton_down:
                    self._mouse_released_once = True
                if self._is_active and self._window:
                    self._outside_poll_job = self._window.after(40, self._check_click_outside)
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
        self._is_streaming = False
        self._trans_label = None
        self._main_frame = None
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
        self._last_q_time: float = 0.0
        self._last_w_time: float = 0.0
        self._trigger_lock = threading.Lock()

    def _trigger_q(self):
        """Dispara callback de Alt+Q com debounce de hardware (250ms)."""
        with self._trigger_lock:
            now = time.perf_counter()
            if (now - self._last_q_time) < 0.25:
                return
            self._last_q_time = now
        if self.callback:
            try:
                threading.Thread(target=self.callback, daemon=True, name="LoTra_Q_Worker").start()
            except Exception as e:
                print(f"[HotkeyListener Alt+Q Error] {e}")

    def _trigger_w(self):
        """Dispara callback de Alt+W com debounce de hardware (250ms)."""
        with self._trigger_lock:
            now = time.perf_counter()
            if (now - self._last_w_time) < 0.25:
                return
            self._last_w_time = now
        if self.on_ocr_snip:
            try:
                threading.Thread(target=self.on_ocr_snip, daemon=True, name="LoTra_W_Worker").start()
            except Exception as e:
                print(f"[HotkeyListener Alt+W Error] {e}")

    def start(self):
        """Inicia escuta em segundo plano."""
        if self.running or sys.platform != "win32":
            return
        self.running = True
        self._thread = threading.Thread(target=self._hotkey_loop, daemon=True, name="LoTra_HotkeyListener")
        self._thread.start()

    def stop(self):
        """Para a escuta de hotkey com desregistro imediato."""
        self.running = False
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=0.3)

    def _hotkey_loop(self):
        user32 = ctypes.windll.user32
        HOTKEY_ID_Q = 101
        HOTKEY_ID_W = 102
        VK_Q = 0x51
        VK_W = 0x57
        MOD_NOREPEAT = 0x4000

        # Tenta registrar estritamente os 2 atalhos: Alt+Q e Alt+W
        reg_q = user32.RegisterHotKey(0, HOTKEY_ID_Q, MOD_ALT | MOD_NOREPEAT, VK_Q)
        if not reg_q:
            reg_q = user32.RegisterHotKey(0, HOTKEY_ID_Q, MOD_ALT, VK_Q)

        reg_w = user32.RegisterHotKey(0, HOTKEY_ID_W, MOD_ALT | MOD_NOREPEAT, VK_W)
        if not reg_w:
            reg_w = user32.RegisterHotKey(0, HOTKEY_ID_W, MOD_ALT, VK_W)

        # Se ambos registraram com sucesso no sistema operacional
        if reg_q and reg_w:
            msg = ctypes.wintypes.MSG()
            try:
                while self.running:
                    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE
                        if msg.message == WM_HOTKEY:
                            if msg.wParam == HOTKEY_ID_Q:
                                self._trigger_q()
                            elif msg.wParam == HOTKEY_ID_W:
                                self._trigger_w()
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.015)
            finally:
                user32.UnregisterHotKey(0, HOTKEY_ID_Q)
                user32.UnregisterHotKey(0, HOTKEY_ID_W)
        else:
            # Se algum atalho falhou no RegisterHotKey (ex: conflito com outro app ou instância anterior),
            # libera o registro parcial e ativa polling de alta precisão com detecção de borda (edge-triggered)
            if reg_q:
                user32.UnregisterHotKey(0, HOTKEY_ID_Q)
            if reg_w:
                user32.UnregisterHotKey(0, HOTKEY_ID_W)

            VK_MENU = 0x12  # ALT
            q_was_down = False
            w_was_down = False

            while self.running:
                alt_down = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
                q_down = (user32.GetAsyncKeyState(VK_Q) & 0x8000) != 0
                w_down = (user32.GetAsyncKeyState(VK_W) & 0x8000) != 0

                # Dispara Alt + Q apenas na transição (apertou agora)
                if alt_down and q_down:
                    if not q_was_down:
                        self._trigger_q()
                # Dispara Alt + W apenas na transição (apertou agora)
                elif alt_down and w_down:
                    if not w_was_down:
                        self._trigger_w()

                q_was_down = (alt_down and q_down)
                w_was_down = (alt_down and w_down)
                time.sleep(0.015)
