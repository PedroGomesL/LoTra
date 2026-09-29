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
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

APP_NAME = "FrankTranslator"

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
            app_dir = Path(xdg_data) / "frank_translator"
        else:
            app_dir = Path.home() / ".local" / "share" / "frank_translator"

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
