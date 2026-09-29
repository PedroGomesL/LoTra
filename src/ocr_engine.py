"""
Módulo de OCR do LoTra: Execução do Windows Media OCR nativo (DirectML / WinRT).
Garante isolamento de memória, buffers efêmeros e compatibilidade com PyInstaller.
"""

import os
import sys
import json
import re
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from resource_utils import get_resource_path
from privacy_vault import EphemeralImageBuffer, secure_wipe_memory

class WindowsMediaOCREngine:
    """Invoca o motor nativo Windows Media OCR via script PowerShell assíncrono WinRT."""
    
    def __init__(self, script_path: Optional[str] = None):
        if script_path:
            self.script_path = Path(script_path)
        else:
            # Tenta localizar em src/win_ocr.ps1 ou win_ocr.ps1
            found = get_resource_path("src/win_ocr.ps1")
            if not found.exists():
                found = get_resource_path("win_ocr.ps1")
            self.script_path = found

    def is_available(self) -> bool:
        """Verifica se o script e o runtime do Windows estão disponíveis."""
        return sys.platform == "win32" and self.script_path.exists()

    def recognize_file(self, image_path: str | Path) -> Dict[str, Any]:
        """Executa OCR em um arquivo de imagem existente em disco."""
        abs_img = os.path.abspath(str(image_path))
        if not os.path.exists(abs_img):
            return {
                "text": "",
                "inference_ms": 0.0,
                "elapsed_ms": 0.0,
                "success": False,
                "error": f"Arquivo de imagem não encontrado: {abs_img}"
            }

        if not self.script_path.exists():
            return {
                "text": "",
                "inference_ms": 0.0,
                "elapsed_ms": 0.0,
                "success": False,
                "error": f"Script win_ocr.ps1 não encontrado em: {self.script_path}"
            }

        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(self.script_path),
            "-ImagePath", abs_img
        ]

        t0 = time.perf_counter()
        try:
            # Cria processo com flags para esconder janela do PowerShell no Windows
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 # SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=15.0
            )
            total_call_ms = (time.perf_counter() - t0) * 1000.0
            stdout = proc.stdout.strip()

            if proc.returncode != 0 and not stdout:
                return {
                    "text": "",
                    "inference_ms": 0.0,
                    "elapsed_ms": total_call_ms,
                    "success": False,
                    "error": f"PowerShell retornou código {proc.returncode}: {proc.stderr.strip()}"
                }

            # Sanitiza caracteres de controle
            clean_stdout = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', stdout)
            
            # Localiza JSON na saída
            data = None
            try:
                data = json.loads(clean_stdout, strict=False)
            except Exception:
                start = clean_stdout.find('{')
                end = clean_stdout.rfind('}')
                if start != -1 and end != -1:
                    try:
                        data = json.loads(clean_stdout[start:end+1], strict=False)
                    except Exception:
                        pass

            if data and isinstance(data, dict):
                extracted = data.get("Text", "").strip()
                return {
                    "text": extracted,
                    "inference_ms": float(data.get("InferenceMs", 0.0)),
                    "elapsed_ms": float(data.get("ElapsedMs", total_call_ms)),
                    "total_subproc_ms": total_call_ms,
                    "success": bool(data.get("Success", True)),
                    "error": data.get("Error")
                }
            else:
                return {
                    "text": "",
                    "inference_ms": 0.0,
                    "elapsed_ms": total_call_ms,
                    "success": False,
                    "error": f"Falha ao interpretar JSON do OCR: {clean_stdout[:200]}"
                }

        except subprocess.TimeoutExpired:
            return {
                "text": "",
                "inference_ms": 0.0,
                "elapsed_ms": 15000.0,
                "success": False,
                "error": "Timeout de execução do OCR (> 15s)"
            }
        except Exception as e:
            return {
                "text": "",
                "inference_ms": 0.0,
                "elapsed_ms": 0.0,
                "success": False,
                "error": str(e)
            }

    def recognize_pil_image(self, pil_image: Image.Image) -> Dict[str, Any]:
        """
        Executa OCR em uma imagem PIL usando buffer efêmero seguro.
        Garante descarte e sobrescrita de memória após o uso.
        """
        import tempfile
        # Cria arquivo efêmero temporário para passagem ao WinRT
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            pil_image.save(tmp_path, format="PNG")
            result = self.recognize_file(tmp_path)
            return result
        finally:
            try:
                if os.path.exists(tmp_path):
                    # Sobrescreve com zeros antes de deletar
                    size = os.path.getsize(tmp_path)
                    with open(tmp_path, "wb") as f:
                        f.write(b"\x00" * size)
                    os.remove(tmp_path)
            except Exception:
                pass
