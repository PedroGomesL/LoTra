"""
Aplicação Central LoTra (Local Translator & Reader Assistant) para Windows:
Integração completa:
- Detecção e Profiler de Hardware dinâmico (CPU AVX2, RAM Win32 API, GPU DirectML / CUDA).
- Windows Media OCR nativo (WinRT DirectML assíncrono).
- Pipeline Adaptativo de Tradução (Cache ACID em SQLite, Ollama LLM, Offline Translator).
- Interface HUD Tooltip flutuante e Hotkey Listener global (Ctrl+Alt+T).
- Proteção anti-vazamento de memória e princípio Read-Only estrito.
"""

import os
import sys
import time
import queue
import threading
from pathlib import Path
from typing import Dict, Any, Optional

# Adiciona diretório src ao sys.path se necessário
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from platform_core import get_app_data_dir, canonicalize_path, HardwareDetector, VRAMManager
from adaptive_engine_orchestrator import HardwareProfiler, AdaptiveEngineOrchestrator
from document_context_vault import DocumentContextVault
from ocr_engine import WindowsMediaOCREngine
from translation_engine import TranslationPipeline
from hud_tooltip import HUDTooltip, HotkeyListener, get_windows_clipboard_text, set_windows_clipboard_text
from resource_utils import get_resource_path

class LoTraApp:
    """Instância central do assistente LoTra."""

    def __init__(self, db_path: Optional[str] = None):
        self.app_data_dir = get_app_data_dir()
        self.vault = DocumentContextVault(db_path=db_path)
        self.ocr_engine = WindowsMediaOCREngine()
        self.translator = TranslationPipeline(vault=self.vault)
        self.hud = HUDTooltip()
        self.hotkey_listener: Optional[HotkeyListener] = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._is_serving: bool = False

    def profile_hardware(self) -> Dict[str, Any]:
        """Inspeciona o hardware da máquina em tempo real e retorna o perfil completo."""
        mem = HardwareProfiler.get_memory_status()
        cpu = HardwareProfiler.get_cpu_info()
        gpu = HardwareProfiler.detect_gpu_capabilities()
        model_tier = HardwareDetector.get_hardware_info()

        return {
            "os": "Windows",
            "cpu_cores": cpu.get("logical_cores", 8),
            "has_avx2": cpu.get("has_avx2", True),
            "total_ram_gb": mem["total_ram_gb"],
            "avail_ram_gb": mem["avail_ram_gb"],
            "ram_used_pct": mem["ram_used_pct"],
            "gpu_name": gpu["gpu_name"],
            "gpu_backend": gpu["backend"],
            "vram_gb": gpu["vram_gb"],
            "recommended_tier": model_tier.get("tier", "small"),
            "recommended_model": model_tier.get("recommended_model", "qwen2.5:1.5b"),
            "decision_reason": model_tier.get("decision_reason", "Hardware-aware profiling")
        }

    def ocr_image(self, image_path: str | Path) -> Dict[str, Any]:
        """Executa reconhecimento óptico de caracteres usando o Windows Media OCR nativo."""
        return self.ocr_engine.recognize_file(image_path)

    def translate_text(self, text: str, doc_hash: str = "quick_translate", target_sla_ms: float = 250.0) -> Dict[str, Any]:
        """Traduz texto utilizando o pipeline adaptativo com cache local."""
        return self.translator.translate_text(text=text, doc_hash=doc_hash, target_sla_ms=target_sla_ms)

    def process_image(self, image_path: str | Path) -> Dict[str, Any]:
        """Pipeline ponta a ponta: OCR de imagem + Tradução do texto extraído."""
        t0 = time.perf_counter()
        ocr_res = self.ocr_image(image_path)
        if not ocr_res.get("success", False) or not ocr_res.get("text"):
            return {
                "success": False,
                "ocr": ocr_res,
                "translation": None,
                "total_pipeline_ms": (time.perf_counter() - t0) * 1000.0,
                "error": ocr_res.get("error", "Nenhum texto detectado na imagem")
            }

        trans_res = self.translate_text(ocr_res["text"])
        total_time = (time.perf_counter() - t0) * 1000.0

        return {
            "success": True,
            "ocr": ocr_res,
            "translation": trans_res,
            "total_pipeline_ms": round(total_time, 2)
        }

    def trigger_quick_translation_from_clipboard(self):
        """Disparado via tecla de atalho ou chamada manual: lê o clipboard, traduz e exibe HUD."""
        clip_text = get_windows_clipboard_text().strip()
        if not clip_text:
            print("[LoTra HUD] Área de transferência vazia.")
            return

        res = self.translate_text(clip_text)

        # Se chamado a partir de uma thread secundária (listener), envia para a fila da UI principal
        # para que todas as operações com Tkinter ocorram exclusivamente na thread da UI.
        if threading.current_thread() is not threading.main_thread():
            self._ui_queue.put(res)
            return

        # Execução na thread principal (CLI direta ou testes)
        self.hud.show(
            translated_text=res["translated_text"],
            source_text=res["source_text"],
            latency_ms=res["latency_ms"],
            engine_name=res["engine_used"],
            timeout_sec=8.0
        )

    def stop_hud_service(self):
        """Para o daemon HUD cooperativamente."""
        self._is_serving = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.hud.destroy()
        VRAMManager.trim_process_memory()

    def start_hud_service(self):
        """Inicia o daemon de segundo plano com escuta de atalho global."""
        print("[LoTra] Iniciando serviço LoTra HUD no Windows...")
        print("[LoTra] Atalhos globais ativados: [Alt + Q] e [Ctrl + Alt + T]")
        print("[LoTra] Dica: Selecione o texto no seu leitor de PDF/livro, copie (Ctrl+C) e pressione Alt+Q.")
        
        self.hotkey_listener = HotkeyListener(callback=self.trigger_quick_translation_from_clipboard)
        self.hotkey_listener.start()
        self._is_serving = True

        # Loop de eventos de UI para o Tkinter HUD na thread principal
        try:
            while self._is_serving:
                # Esvazia a fila de eventos vindos do HotkeyListener em segundo plano
                while not self._ui_queue.empty():
                    try:
                        res = self._ui_queue.get_nowait()
                        self.hud.show(
                            translated_text=res["translated_text"],
                            source_text=res["source_text"],
                            latency_ms=res["latency_ms"],
                            engine_name=res["engine_used"],
                            timeout_sec=8.0
                        )
                    except queue.Empty:
                        break

                self.hud.pump_events()
                time.sleep(0.04)
        except KeyboardInterrupt:
            print("\n[LoTra] Encerrando serviço...")
        finally:
            self.stop_hud_service()

    def run_self_test(self) -> Dict[str, Any]:
        """Executa auto-diagnóstico completo de integridade de todos os subsistemas."""
        results = {}

        # 1. Hardware Profiling
        try:
            hw = self.profile_hardware()
            results["hardware_profiler"] = {
                "status": "PASS",
                "details": f"CPU Cores: {hw['cpu_cores']} | RAM: {hw['total_ram_gb']}GB (Livre: {hw['avail_ram_gb']}GB) | GPU: {hw['gpu_name']} | Tier: {hw['recommended_tier']}"
            }
        except Exception as e:
            results["hardware_profiler"] = {"status": "FAIL", "error": str(e)}

        # 2. Vault Health Check
        try:
            vault_check = self.vault.health_check()
            results["document_context_vault"] = {
                "status": "PASS" if vault_check.get("integrity") == "ok" or vault_check.get("status") == "new" else "FAIL",
                "details": vault_check
            }
        except Exception as e:
            results["document_context_vault"] = {"status": "FAIL", "error": str(e)}

        # 3. Translation Pipeline & Cache Check
        try:
            sample_phrase = "quantum scalability"
            tr1 = self.translate_text(sample_phrase)
            tr2 = self.translate_text(sample_phrase) # Deve atingir o cache ACID
            results["translation_pipeline"] = {
                "status": "PASS" if tr1["translated_text"] and tr2["cache_hit"] else "FAIL",
                "first_run_ms": tr1["latency_ms"],
                "cache_hit_ms": tr2["latency_ms"],
                "cache_verified": tr2["cache_hit"],
                "translated_output": tr2["translated_text"]
            }
        except Exception as e:
            results["translation_pipeline"] = {"status": "FAIL", "error": str(e)}

        # 4. Windows Media OCR Script Availability
        try:
            ocr_ready = self.ocr_engine.is_available()
            results["win_ocr_engine"] = {
                "status": "PASS" if ocr_ready else "WARN",
                "script_path": str(self.ocr_engine.script_path),
                "script_exists": self.ocr_engine.script_path.exists()
            }
        except Exception as e:
            results["win_ocr_engine"] = {"status": "FAIL", "error": str(e)}

        # 5. Resource Utils & Asset Resolution
        try:
            ico_path = get_resource_path("assets/lotra.ico")
            results["resource_resolution"] = {
                "status": "PASS" if ico_path.exists() else "WARN",
                "icon_path": str(ico_path),
                "icon_exists": ico_path.exists()
            }
        except Exception as e:
            results["resource_resolution"] = {"status": "FAIL", "error": str(e)}

        all_passed = all(v["status"] in ("PASS", "WARN") for v in results.values())
        return {
            "all_passed": all_passed,
            "subsystems": results
        }
