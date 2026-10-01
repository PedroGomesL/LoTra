"""
Módulo de Plataforma Multi-OS e Abstração de Sistema (Platform Core).
Inspirado na arquitetura frank_sherlock:
- Isolamento absoluto de dados da aplicação em diretório de usuário do SO (Read-Only nos docs).
- Canonicalização de caminhos (tratamento especial para prefixos UNC \\?\\ do Windows).
- Detecção de Hardware e Seleção de Modelos Tiered (qwen2.5vl: 3b/7b/32b) com cache no AppState.
- Limpeza e descarga explícita de modelos da VRAM (Ollama unloader).
- Provisionamento de ambiente isolado (venv) em AppData para motores externos (Surya OCR).
"""

import os
import sys
import platform
import shutil
import subprocess
import urllib.request
import json
import gc
import ctypes
import threading
import socket
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

APP_NAME = "LoTra"

def get_app_data_dir() -> Path:
    """
    Retorna o diretório isolado de dados do aplicativo no SO.
    Garante o Princípio Read-Only: NENHUM arquivo de cache, banco de dados ou thumbnail
    é escrito nos diretórios de documentos do usuário.
    - Windows: %LOCALAPPDATA%\\FrankTranslator (ex: C:\\Users\\...\\AppData\\Local\\FrankTranslator)
    - Linux: ~/.local/share/frank_translator (ou $XDG_DATA_HOME/frank_translator)
    - macOS: ~/Library/Application Support/FrankTranslator
    """
    system = platform.system()
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data)
        else:
            base_dir = Path.home() / "AppData" / "Local"
        app_dir = base_dir / APP_NAME
    elif system == "Darwin":
        app_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    else: # Linux / Unix
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            app_dir = Path(xdg_data) / "lotra"
        else:
            app_dir = Path.home() / ".local" / "share" / "lotra"

    # Garante existência das subpastas isoladas
    (app_dir / "db").mkdir(parents=True, exist_ok=True)
    (app_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
    (app_dir / "cache").mkdir(parents=True, exist_ok=True)
    (app_dir / "backups").mkdir(parents=True, exist_ok=True)
    (app_dir / "surya_venv").mkdir(parents=True, exist_ok=True)

    return app_dir

def canonicalize_path(file_path: str | Path) -> str:
    """
    Canonicaliza o caminho removendo inconsistências de OS.
    No Windows, caminhos longos geram o prefixo '\\\\?\\' ou '\\\\?\\UNC\\'.
    Normaliza para formato uniforme para evitar quebras em comparações de string
    ou em chamadas de subprocessos e bibliotecas nativas (análogo ao dunce::canonicalize em Rust).
    """
    p_str = str(file_path)
    
    # Tratamento de prefixos estendidos do Windows
    if platform.system() == "Windows":
        if p_str.startswith("\\\\?\\UNC\\"):
            p_str = "\\\\" + p_str[8:]
        elif p_str.startswith("\\\\?\\"):
            p_str = p_str[4:]
            
    # Resolve caminho absoluto e normaliza separadores
    try:
        norm = os.path.abspath(p_str)
        # Normaliza maiúsculas/minúsculas da letra de unidade no Windows (ex: c:\ -> C:\)
        if len(norm) >= 2 and norm[1] == ":":
            norm = norm[0].upper() + norm[1:]
        return norm
    except Exception:
        return p_str

class HardwareDetector:
    """
    Detecção de Hardware Aware:
    Detecta GPU/RAM no startup e faz cache no AppState para não executar subprocessos repetidamente.
    Seleciona a família de modelos ideal:
    - GPU fraca ou sem GPU (< 6GB VRAM): Tier Small (qwen2.5vl:3b)
    - GPU com >= 6GB VRAM: Tier Medium (qwen2.5vl:7b)
    - Apple Silicon com >= 48GB memória unificada: Tier Large (qwen2.5vl:32b)
    """
    _cached_hardware: Optional[Dict[str, Any]] = None

    @classmethod
    def get_hardware_info(cls, force_refresh: bool = False) -> Dict[str, Any]:
        if cls._cached_hardware is not None and not force_refresh:
            return cls._cached_hardware

        system = platform.system()
        total_ram_gb = 16.0
        avail_ram_gb = 8.0
        gpu_detected = False
        gpu_name = "CPU Only"
        vram_gb = 0.0
        is_apple_silicon = False

        # 1. Detecção de RAM do Sistema
        if system == "Windows":
            try:
                from adaptive_engine_orchestrator import HardwareProfiler
                mem = HardwareProfiler.get_memory_status()
                total_ram_gb = mem["total_ram_gb"]
                avail_ram_gb = mem["avail_ram_gb"]
            except Exception:
                pass
        else:
            try:
                import psutil
                vm = psutil.virtual_memory()
                total_ram_gb = round(vm.total / (1024 ** 3), 2)
                avail_ram_gb = round(vm.available / (1024 ** 3), 2)
            except Exception:
                pass

        # 2. Detecção de GPU
        # 2.1 macOS Apple Silicon (system_profiler)
        if system == "Darwin":
            try:
                proc = subprocess.run(["system_profiler", "SPHardwareDataType"], capture_output=True, text=True, timeout=2)
                if "Apple" in proc.stdout:
                    is_apple_silicon = True
                    gpu_name = "Apple Silicon Unified Memory"
                    vram_gb = total_ram_gb
                    gpu_detected = True
            except Exception:
                pass

        # 2.2 NVIDIA GPU (nvidia-smi) no Windows ou Linux
        if not gpu_detected:
            try:
                proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    line = proc.stdout.strip().split("\n")[0]
                    parts = line.split(",")
                    gpu_name = parts[0].strip()
                    vram_mb = float(parts[1].strip())
                    vram_gb = round(vram_mb / 1024.0, 2)
                    gpu_detected = True
            except Exception:
                pass

        # 2.3 DirectML / AMD iGPU no Windows (fallback se não tem nvidia-smi)
        if not gpu_detected and system == "Windows":
            try:
                from adaptive_engine_orchestrator import HardwareProfiler
                gpu_prof = HardwareProfiler.detect_gpu_capabilities()
                if gpu_prof.get("has_cuda"):
                    gpu_detected = True
                    gpu_name = gpu_prof["gpu_name"]
                    vram_gb = gpu_prof["vram_gb"]
                else:
                    gpu_name = gpu_prof.get("gpu_name", "AMD Radeon / DirectML")
                    vram_gb = gpu_prof.get("vram_gb", 2.0)
            except Exception:
                pass

        # 3. Seleção de Modelo Hardware-Aware
        if is_apple_silicon and total_ram_gb >= 48.0:
            tier = "large"
            recommended_model = "qwen2.5vl:32b"
            reason = f"Apple Silicon com {total_ram_gb}GB unificados: Tier Large sem risco de swap"
        elif gpu_detected and vram_gb >= 6.0:
            tier = "medium"
            recommended_model = "qwen2.5vl:7b"
            reason = f"GPU com {vram_gb}GB VRAM (>= 6GB): Tier Medium com excelente fidelidade"
        else:
            tier = "small"
            recommended_model = "qwen2.5vl:3b"
            reason = f"GPU de entrada ou CPU ({vram_gb}GB VRAM): Tier Small rápido e leve"

        info = {
            "os": system,
            "architecture": platform.machine(),
            "cpu_cores": os.cpu_count() or 4,
            "total_ram_gb": total_ram_gb,
            "avail_ram_gb": avail_ram_gb,
            "gpu_detected": gpu_detected,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb,
            "is_apple_silicon": is_apple_silicon,
            "tier": tier,
            "recommended_model": recommended_model,
            "decision_reason": reason
        }

        cls._cached_hardware = info
        return info

class VRAMManager:
    """
    Gerenciamento de VRAM e descarregamento explícito de modelos:
    Ao terminar classificações ou traduções, descarrega o modelo da VRAM
    (via Ollama keep_alive: 0) para não monopolizar a GPU do usuário.
    """
    @staticmethod
    def unload_ollama_models(ollama_url: str = "http://127.0.0.1:11434", model_name: Optional[str] = None) -> bool:
        """
        Envia requisição para o Ollama com keep_alive: 0,
        forçando a liberação imediata da memória de vídeo (VRAM).
        """
        target_model = model_name or "qwen2.5vl:7b"
        endpoint = f"{ollama_url}/api/generate"
        payload = json.dumps({
            "model": target_model,
            "keep_alive": 0
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                return resp.status == 200
        except Exception:
            # Se o serviço Ollama local não estiver rodando no momento, retorna false gracefully
            return False

    @staticmethod
    def trim_process_memory():
        """Libera heap não utilizado e solicita ao SO o esvaziamento do working set de RAM."""
        gc.collect()
        if platform.system() == "Windows":
            try:
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.EmptyWorkingSet(handle)
            except Exception:
                pass

class EnvironmentProvisioner:
    """
    Provisionamento de venv Python isolado em AppData para motores externos (ex: Surya OCR).
    O app nunca polui o Python do sistema e mantém dependências isoladas.
    """
    @staticmethod
    def get_venv_python_path(venv_dir: Optional[Path] = None) -> Path:
        target_dir = venv_dir or (get_app_data_dir() / "surya_venv")
        if platform.system() == "Windows":
            return target_dir / "Scripts" / "python.exe"
        else:
            return target_dir / "bin" / "python"

    @staticmethod
    def is_venv_ready(venv_dir: Optional[Path] = None) -> bool:
        py_path = EnvironmentProvisioner.get_venv_python_path(venv_dir)
        return py_path.exists() and os.access(str(py_path), os.X_OK)

    @staticmethod
    def provision_venv(venv_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Cria o ambiente venv se ainda não existir."""
        target_dir = venv_dir or (get_app_data_dir() / "surya_venv")
        py_bin = EnvironmentProvisioner.get_venv_python_path(target_dir)

        if EnvironmentProvisioner.is_venv_ready(target_dir):
            return {"status": "ready", "path": str(py_bin), "created": False}

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        # Usa o Python do executável atual para criar o venv
        cmd = [sys.executable, "-m", "venv", str(target_dir)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and py_bin.exists():
                return {"status": "ready", "path": str(py_bin), "created": True}
            return {"status": "error", "error": res.stderr}
        except Exception as e:
            return {"status": "error", "error": str(e)}

from abc import ABC, abstractmethod

class IPlatformBridge(ABC):
    """
    Interface abstrata do Platform Bridge para desacoplamento de chamadas nativas do SO.
    Permite execução modularizada no Windows, Linux (X11 / Wayland) e macOS.
    """

    @abstractmethod
    def get_clipboard_text(self) -> str:
        """Lê texto da área de transferência."""
        pass

    @abstractmethod
    def set_clipboard_text(self, text: str) -> bool:
        """Grava texto na área de transferência."""
        pass

    @abstractmethod
    def simulate_copy_selection(self, timeout_sec: float = 0.35) -> str:
        """Captura a seleção ativa na janela em primeiro plano."""
        pass

    @abstractmethod
    def get_monitor_work_area_for_point(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """Retorna (left, top, right, bottom) da área de trabalho do monitor no ponto (x, y)."""
        pass

    @abstractmethod
    def get_dpi_for_point(self, x: int, y: int) -> int:
        """Retorna o DPI do monitor no ponto (x, y) ou 96."""
        pass

    @abstractmethod
    def is_process_elevated(self) -> bool:
        """Verifica se o processo atual possui privilégios administrativos."""
        pass

    @abstractmethod
    def is_foreground_window_elevated(self) -> bool:
        """Verifica se a janela ativa está rodando com privilégios elevados."""
        pass

    @abstractmethod
    def supports_native_snipping(self) -> bool:
        """Verifica se o SO suporta recorte nativo via ferramenta do sistema."""
        pass


class WindowsPlatformBridge(IPlatformBridge):
    """Implementação nativa do Windows utilizando APIs Win32 (user32, kernel32, shell32, shcore)."""

    def get_clipboard_text(self) -> str:
        from hud_tooltip import get_windows_clipboard_text
        return get_windows_clipboard_text()

    def set_clipboard_text(self, text: str) -> bool:
        from hud_tooltip import set_windows_clipboard_text
        return set_windows_clipboard_text(text)

    def simulate_copy_selection(self, timeout_sec: float = 0.35) -> str:
        from hud_tooltip import simulate_copy_selection
        return simulate_copy_selection(timeout_sec)

    def get_monitor_work_area_for_point(self, x: int, y: int) -> Tuple[int, int, int, int]:
        from hud_tooltip import get_monitor_work_area_for_point
        return get_monitor_work_area_for_point(x, y)

    def get_dpi_for_point(self, x: int, y: int) -> int:
        from hud_tooltip import get_dpi_for_point
        return get_dpi_for_point(x, y)

    def is_process_elevated(self) -> bool:
        from hud_tooltip import is_process_elevated
        return is_process_elevated()

    def is_foreground_window_elevated(self) -> bool:
        from hud_tooltip import is_foreground_window_elevated
        return is_foreground_window_elevated()

    def supports_native_snipping(self) -> bool:
        return True


class LinuxPlatformBridge(IPlatformBridge):
    """Implementação modular para Linux suportando sessões X11 e Wayland."""

    def __init__(self):
        self.session_type = os.environ.get("XDG_SESSION_TYPE", "x11").lower()

    def get_clipboard_text(self) -> str:
        try:
            if self.session_type == "wayland" and shutil.which("wl-paste"):
                res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0:
                    return res.stdout
            elif shutil.which("xclip"):
                res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0:
                    return res.stdout
            elif shutil.which("xsel"):
                res = subprocess.run(["xsel", "--clipboard", "--output"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0:
                    return res.stdout
        except Exception:
            pass
        return ""

    def set_clipboard_text(self, text: str) -> bool:
        try:
            if self.session_type == "wayland" and shutil.which("wl-copy"):
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"), timeout=1.0)
                return p.returncode == 0
            elif shutil.which("xclip"):
                p = subprocess.Popen(["xclip", "-selection", "clipboard", "-i"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"), timeout=1.0)
                return p.returncode == 0
            elif shutil.which("xsel"):
                p = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"), timeout=1.0)
                return p.returncode == 0
        except Exception:
            pass
        return False

    def simulate_copy_selection(self, timeout_sec: float = 0.35) -> str:
        # No Linux (X11/Wayland), a seleção primária do mouse já disponibiliza o texto sem Ctrl+C!
        try:
            if self.session_type == "wayland" and shutil.which("wl-paste"):
                res = subprocess.run(["wl-paste", "--primary", "--no-newline"], capture_output=True, text=True, timeout=0.5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
            elif shutil.which("xclip"):
                res = subprocess.run(["xclip", "-selection", "primary", "-o"], capture_output=True, text=True, timeout=0.5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
            elif shutil.which("xsel"):
                res = subprocess.run(["xsel", "--primary", "--output"], capture_output=True, text=True, timeout=0.5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
        except Exception:
            pass
        return self.get_clipboard_text()

    def get_monitor_work_area_for_point(self, x: int, y: int) -> Tuple[int, int, int, int]:
        return (0, 0, 1920, 1080)

    def get_dpi_for_point(self, x: int, y: int) -> int:
        return 96

    def is_process_elevated(self) -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def is_foreground_window_elevated(self) -> bool:
        return False

    def supports_native_snipping(self) -> bool:
        return bool(shutil.which("grim") or shutil.which("gnome-screenshot") or shutil.which("scrot"))


class MacOSPlatformBridge(IPlatformBridge):
    """Implementação modular para macOS via pbcopy, pbpaste e Accessibility API."""

    def get_clipboard_text(self) -> str:
        try:
            res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
        return ""

    def set_clipboard_text(self, text: str) -> bool:
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"), timeout=1.0)
            return p.returncode == 0
        except Exception:
            pass
        return False

    def simulate_copy_selection(self, timeout_sec: float = 0.35) -> str:
        return self.get_clipboard_text()

    def get_monitor_work_area_for_point(self, x: int, y: int) -> Tuple[int, int, int, int]:
        return (0, 0, 1920, 1080)

    def get_dpi_for_point(self, x: int, y: int) -> int:
        return 96

    def is_process_elevated(self) -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def is_foreground_window_elevated(self) -> bool:
        return False

    def supports_native_snipping(self) -> bool:
        return bool(shutil.which("screencapture"))


_PLATFORM_BRIDGE_INSTANCE: Optional[IPlatformBridge] = None

def get_platform_bridge() -> IPlatformBridge:
    """Retorna o singleton do Platform Bridge correspondente ao sistema operacional em execução."""
    global _PLATFORM_BRIDGE_INSTANCE
    if _PLATFORM_BRIDGE_INSTANCE is not None:
        return _PLATFORM_BRIDGE_INSTANCE

    sys_plat = platform.system()
    if sys_plat == "Windows":
        _PLATFORM_BRIDGE_INSTANCE = WindowsPlatformBridge()
    elif sys_plat == "Darwin":
        _PLATFORM_BRIDGE_INSTANCE = MacOSPlatformBridge()
    else:
        _PLATFORM_BRIDGE_INSTANCE = LinuxPlatformBridge()

    return _PLATFORM_BRIDGE_INSTANCE


class SingleInstanceGuard:
    """
    Garante que apenas uma única instância do processo LoTra execute simultaneamente no Windows,
    utilizando um Mutex nomeado no kernel do Win32.
    Evita acúmulo de múltiplos processos .exe no Gerenciador de Tarefas e conflitos de atalhos globais.
    """

    def __init__(self, mutex_name: str = "LoTra_SingleInstance_Mutex_Global"):
        self.mutex_name = mutex_name
        self.mutex = None
        self._is_primary = False

    def acquire(self) -> bool:
        """Tenta adquirir o mutex exclusivo. Retorna True se for a instância primária, False se já houver outra rodando."""
        if sys.platform != "win32":
            self._is_primary = True
            return True

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        self.mutex = kernel32.CreateMutexW(None, False, self.mutex_name)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            self._is_primary = False
            return False

        self._is_primary = True
        return True

    def activate_existing_window(self, window_title_substr: str = "LoTra"):
        """Localiza e traz para frente a janela da instância que já está em execução."""
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32

        def enum_windows_callback(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    val = buff.value
                    if window_title_substr.lower() in val.lower():
                        # SW_RESTORE = 9
                        user32.ShowWindow(hwnd, 9)
                        user32.SetForegroundWindow(hwnd)
                        return False
            return True

        try:
            import ctypes.wintypes
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            cb = WNDENUMPROC(enum_windows_callback)
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

    def release(self):
        """Libera o mutex ao encerrar a aplicação."""
        if self.mutex and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex)
            except Exception:
                pass
            self.mutex = None
            self._is_primary = False


# =========================================================================
# Gerenciamento de Processos com Windows Job Objects (Zero-Friction Engine)
# =========================================================================

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJobObject:
    """
    Gerenciador de Ciclo de Vida de Processos com Windows Job Objects (Win32 API).
    Garante que qualquer processo filho (como servidores locais de LLM, Ollama, etc.)
    seja sumariamente encerrado pelo kernel do Windows caso o processo pai seja finalizado,
    fechado pelo usuário ou sofra encerramento inesperado, impedindo processos zumbis
    e vazamento de VRAM/RAM no sistema.
    """

    def __init__(self, name: Optional[str] = None):
        self.handle = None
        self._is_active = False
        if sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32
                self.handle = kernel32.CreateJobObjectW(None, name)
                if self.handle:
                    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    success = kernel32.SetInformationJobObject(
                        self.handle,
                        JobObjectExtendedLimitInformation,
                        ctypes.byref(info),
                        ctypes.sizeof(info)
                    )
                    self._is_active = bool(success)
            except Exception:
                self.handle = None
                self._is_active = False

    def assign_process(self, proc_or_handle) -> bool:
        """Associa um subprocesso ao Job Object."""
        if not self.handle or sys.platform != "win32":
            return False
        try:
            kernel32 = ctypes.windll.kernel32
            if hasattr(proc_or_handle, "_handle"):
                raw_handle = int(proc_or_handle._handle)
            elif isinstance(proc_or_handle, int):
                PROCESS_ALL_ACCESS = 0x1F0FFF
                raw_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, proc_or_handle)
            else:
                raw_handle = int(proc_or_handle)

            res = kernel32.AssignProcessToJobObject(self.handle, raw_handle)
            return bool(res)
        except Exception:
            return False

    def close(self):
        """Fecha o handle do Job Object. Com JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, encerra os processos filhos."""
        if self.handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
            self._is_active = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class LocalNeuralEngineManager:
    """
    Gerenciador com 'Zero Atrito' de Motor Neural Local (LLM).
    - Descoberta automática de binários locais (Ollama, etc.).
    - Execução sem janelas de console e com contenção via Windows Job Objects.
    - Zero vazamento de RAM/VRAM: descarregamento explícito e término limpo.
    - Modo resiliente: se nenhum motor local for detectado, mantém LoTra 100% funcional
      utilizando o motor offline contextual embutido de latência sub-milissegundo.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11434):
        self.host = host
        self.port = port
        self.api_url = f"http://{host}:{port}"
        self.job_object: Optional[WindowsJobObject] = None
        self._managed_proc: Optional[subprocess.Popen] = None
        self._binary_path: Optional[str] = None
        self._neural_enabled: bool = True
        self._lock = threading.Lock()

    def find_binary(self) -> Optional[str]:
        """Localiza o binário do Ollama no PATH ou em diretórios comuns de instalação no Windows."""
        if self._binary_path and Path(self._binary_path).exists():
            return self._binary_path

        found = shutil.which("ollama")
        if found and Path(found).exists():
            self._binary_path = canonicalize_path(found)
            return self._binary_path

        local_app_data = os.environ.get("LOCALAPPDATA")
        candidates = []
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe")
        candidates.append(Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe")
        candidates.append(Path("C:/Program Files/Ollama/ollama.exe"))
        candidates.append(Path("C:/Program Files (x86)/Ollama/ollama.exe"))

        for c in candidates:
            if c.exists():
                self._binary_path = canonicalize_path(c)
                return self._binary_path

        return None

    def is_installed(self) -> bool:
        """Verifica se o Ollama está instalado no sistema operacional."""
        return self.find_binary() is not None

    def is_server_listening(self) -> bool:
        """Verifica se o servidor Ollama está respondendo na porta local (< 40ms)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.040)
                return s.connect_ex((self.host, self.port)) == 0
        except Exception:
            return False

    def is_neural_enabled(self) -> bool:
        return self._neural_enabled

    def set_neural_enabled(self, enabled: bool):
        self._neural_enabled = bool(enabled)

    def get_available_models(self) -> List[str]:
        """Consulta modelos locais já baixados no Ollama."""
        if not self.is_server_listening():
            return []
        try:
            req = urllib.request.Request(f"{self.api_url}/api/tags", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                    return models
        except Exception:
            pass
        return []

    def start_engine(self) -> Dict[str, Any]:
        """Inicia o servidor de IA local sob o controle estrito de Windows Job Object."""
        with self._lock:
            if self.is_server_listening():
                models = self.get_available_models()
                return {
                    "success": True,
                    "status": "already_running",
                    "message": f"Motor neural já está ativo ({len(models)} modelo(s) disponível(is)).",
                    "models": models,
                    "managed_by_lotra": False
                }

            bin_path = self.find_binary()
            if not bin_path or not Path(bin_path).exists():
                return {
                    "success": False,
                    "status": "not_installed",
                    "message": "Ollama não localizado. Operando em modo offline integrado sem atrito.",
                    "models": [],
                    "managed_by_lotra": False
                }

            try:
                self.job_object = WindowsJobObject()
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

                self._managed_proc = subprocess.Popen(
                    [bin_path, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags
                )

                if self.job_object._is_active:
                    self.job_object.assign_process(self._managed_proc)

                # Aguarda até 3.5 segundos para o servidor responder
                t0 = time.time()
                listening = False
                while time.time() - t0 < 3.5:
                    if self.is_server_listening():
                        listening = True
                        break
                    time.sleep(0.2)

                models = self.get_available_models() if listening else []
                return {
                    "success": True,
                    "status": "started" if listening else "starting",
                    "pid": self._managed_proc.pid,
                    "message": "Motor neural iniciado com sucesso sob contenção Job Object.",
                    "models": models,
                    "managed_by_lotra": True
                }
            except Exception as e:
                return {
                    "success": False,
                    "status": "error",
                    "message": f"Falha ao iniciar motor neural: {e}",
                    "models": [],
                    "managed_by_lotra": False
                }

    def stop_engine(self) -> Dict[str, Any]:
        """Encerra o servidor e descarrega a VRAM com proteção anti-vazamento de memória."""
        with self._lock:
            # 1. Solicita descarregamento imediato da VRAM para a GPU
            VRAMManager.unload_ollama_models(ollama_url=self.api_url)

            was_managed = False
            if self._managed_proc:
                was_managed = True
                try:
                    self._managed_proc.terminate()
                    self._managed_proc.wait(timeout=1.5)
                except Exception:
                    try:
                        self._managed_proc.kill()
                    except Exception:
                        pass
                self._managed_proc = None

            if self.job_object:
                self.job_object.close()
                self.job_object = None

            VRAMManager.trim_process_memory()

            msg = "Motor neural encerrado e memória VRAM/RAM liberada com sucesso." if was_managed else "Memória de GPU (VRAM) e cache liberados com sucesso."
            return {
                "success": True,
                "status": "stopped",
                "message": msg,
                "managed_by_lotra": False
            }

    def unload_vram(self, model_name: Optional[str] = None) -> bool:
        """Descarrega modelo da GPU sem encerrar o processo servidor."""
        res = VRAMManager.unload_ollama_models(ollama_url=self.api_url, model_name=model_name)
        VRAMManager.trim_process_memory()
        return res

    def get_status(self) -> Dict[str, Any]:
        """Retorna o status completo para a interface do usuário."""
        installed = self.is_installed()
        running = self.is_server_listening()
        models = self.get_available_models() if running else []
        managed = self._managed_proc is not None

        if running:
            disp = f"[ATIVO] Motor Neural Local ({len(models)} modelo(s) pronto(s))"
        elif installed:
            disp = "[INATIVO] Motor Local Inativo (Modo Offline Integrado Ativo)"
        else:
            disp = "[OFFLINE] Modo Offline Integrado (Ollama nao detectado)"

        return {
            "installed": installed,
            "running": running,
            "binary_path": self.find_binary(),
            "models": models,
            "managed_by_lotra": managed,
            "neural_enabled": self._neural_enabled,
            "display_text": disp
        }


_NEURAL_ENGINE_MANAGER: Optional[LocalNeuralEngineManager] = None

def get_neural_engine_manager() -> LocalNeuralEngineManager:
    """Retorna o singleton do gerenciador de motor neural local."""
    global _NEURAL_ENGINE_MANAGER
    if _NEURAL_ENGINE_MANAGER is None:
        _NEURAL_ENGINE_MANAGER = LocalNeuralEngineManager()
    return _NEURAL_ENGINE_MANAGER


