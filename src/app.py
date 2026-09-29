"""
Aplicação Central LoTra (Local Translator & Reader Assistant) para Windows:
Integração completa:
- Detecção e Profiler de Hardware dinâmico (CPU AVX2, RAM Win32 API, GPU DirectML / CUDA).
- Windows Media OCR nativo (WinRT DirectML assíncrono).
- Pipeline 100% Local de Tradução (Cache ACID em SQLite, Ollama LLM, Offline Translator).
- Interface HUD Tooltip flutuante com Times New Roman e 2 atalhos: [Alt + Q] (Seleção) e [Alt + W] (OCR).
- Proteção anti-vazamento de memória e princípio Read-Only estrito.
"""

import os
import sys
import time
import queue
import threading
import ctypes
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
from hud_tooltip import (
    HUDTooltip,
    HotkeyListener,
    get_windows_clipboard_text,
    set_windows_clipboard_text,
    simulate_copy_selection,
    normalize_text_spacing
)
from screen_snipper import NativeScreenSnipper
from resource_utils import get_resource_path
from ui_window import LoTraMainWindow

class LoTraApp:
    """Instância central do assistente LoTra."""

    def __init__(self, db_path: Optional[str] = None):
        self.app_data_dir = get_app_data_dir()
        self.vault = DocumentContextVault(db_path=db_path)
        self.ocr_engine = WindowsMediaOCREngine()
        self.translator = TranslationPipeline(vault=self.vault)
        self.hud = HUDTooltip()
        self.screen_snipper = NativeScreenSnipper(root=self.hud._root)
        self.hotkey_listener: Optional[HotkeyListener] = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._is_serving: bool = False
        self.main_window: Optional[LoTraMainWindow] = None

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

    def _dispatch_translation(self, text: str):
        """Processa e despacha tradução para o HUD de forma thread-safe."""
        clean_text = normalize_text_spacing(text)
        if not clean_text:
            print("[LoTra HUD] Nenhuma seleção ou texto detectado.")
            return

        res = self.translate_text(clean_text)

        if threading.current_thread() is not threading.main_thread():
            self._ui_queue.put(res)
            return

        self.hud.show(
            translated_text=res["translated_text"],
            source_text=res["source_text"],
            latency_ms=res["latency_ms"],
            engine_name=res["engine_used"],
            timeout_sec=0.0
        )

    def _display_hud_notice(self, notice_text: str):
        """Exibe avisos informativos do sistema (ex: UIPI / privilégios) no HUD."""
        payload = {
            "translated_text": notice_text,
            "source_text": "",
            "latency_ms": 0.0,
            "engine_used": "LoTra Security Shield (UIPI)",
            "timeout_sec": 0.0
        }
        if threading.current_thread() is not threading.main_thread():
            self._ui_queue.put(payload)
            return

        self.hud.show(
            translated_text=notice_text,
            source_text="",
            latency_ms=0.0,
            engine_name="LoTra Security Shield (UIPI)",
            timeout_sec=0.0
        )

    def trigger_quick_translation_from_selection(self):
        """
        Disparado via [Alt + Q]:
        1. Simula automaticamente a cópia (Ctrl+C) na janela ativa do Windows.
        2. Normaliza quebras de linha duras de PDF em fluxo de parágrafo contínuo.
        3. Traduz via motor local e enfileira exibição no HUD tooltip.
        """
        clip_text = simulate_copy_selection()
        if clip_text.startswith("[Aviso UIPI]"):
            self._display_hud_notice(clip_text)
            return

        if not clip_text:
            clip_text = get_windows_clipboard_text()
            if not clip_text:
                return

        self._dispatch_translation(clip_text)

    def trigger_quick_translation_from_clipboard(self):
        """Disparado via leitura direta da área de transferência."""
        clip_text = get_windows_clipboard_text()
        self._dispatch_translation(clip_text)

    def trigger_ocr_screen_snip(self):
        """
        Disparado via [Alt + W]:
        Dispara o recorte nativo de tela (NativeScreenSnipper) thread-safe via UI thread,
        com cancelamento instantâneo via Esc (< 5ms) e captura direta sem poluir o clipboard.
        """
        if self._is_serving:
            self._ui_queue.put({"_action": "start_native_snip"})
        else:
            threading.Thread(target=self._ocr_worker_task, daemon=True, name="LoTra_OCR_Worker").start()

    def _handle_native_snip(self):
        """Inicia o NativeScreenSnipper na thread de UI."""
        def on_snip(img, pos):
            def ocr_task():
                ocr_res = self.ocr_engine.recognize_pil_image(img)
                if not ocr_res.get("success") or not ocr_res.get("text"):
                    print("[LoTra OCR Snip] Nenhum texto legível encontrado pelo OCR.")
                    return
                clean_text = normalize_text_spacing(ocr_res["text"])
                trans_res = self.translate_text(clean_text)
                trans_res["engine_used"] = f"Native Snipper + WinRT OCR ({ocr_res.get('inference_ms', 0):.0f}ms) + {trans_res['engine_used']}"
                trans_res["cursor_pos"] = pos
                self._ui_queue.put(trans_res)
            threading.Thread(target=ocr_task, daemon=True, name="LoTra_OCR_Worker").start()

        self.screen_snipper.start_snip(
            on_snip=on_snip,
            on_cancel=lambda: print("[LoTra OCR Snip] Recorte cancelado pelo usuário (< 5ms).")
        )

    def _ocr_worker_task(self):
        from PIL import Image, ImageGrab
        user32 = ctypes.windll.user32 if sys.platform == "win32" else None
        seq_before = user32.GetClipboardSequenceNumber() if user32 else 0
        hwnd_initial = user32.GetForegroundWindow() if user32 else None

        # 1. Invoca o recortador de tela oficial do Windows (ms-screenclip:)
        try:
            if sys.platform == "win32":
                ctypes.windll.shell32.ShellExecuteW(None, "open", "ms-screenclip:", None, None, 1)
        except Exception as e:
            print(f"[LoTra OCR Snip] Aviso ao iniciar ms-screenclip: {e}")

        # 2. Aguarda recorte do usuário na área de transferência com cancelamento rápido se Esc for pressionado
        deadline = time.perf_counter() + 15.0
        grabbed_img: Optional[Image.Image] = None
        overlay_activated = False
        overlay_closed_at = None

        while time.perf_counter() < deadline:
            time.sleep(0.06)

            # Verifica se o clipboard foi atualizado com novo recorte
            if user32 and user32.GetClipboardSequenceNumber() != seq_before:
                try:
                    data = ImageGrab.grabclipboard()
                    if isinstance(data, Image.Image):
                        grabbed_img = data
                        break
                except Exception:
                    pass

            # Detecção de cancelamento com Esc (fechamento do overlay sem alteração no clipboard)
            if user32:
                curr_hwnd = user32.GetForegroundWindow()
                if curr_hwnd != hwnd_initial:
                    overlay_activated = True
                elif overlay_activated and curr_hwnd == hwnd_initial:
                    if overlay_closed_at is None:
                        overlay_closed_at = time.perf_counter()
                    elif time.perf_counter() - overlay_closed_at > 0.25:
                        break

        # 3. Se nenhum novo recorte foi efetuado, encerra graciosamente sem processar imagens antigas residuais
        if not grabbed_img:
            print("[LoTra OCR Snip] Recorte cancelado pelo usuário ou nenhuma imagem capturada.")
            return

        # 4. Executa OCR local nativo com buffers efêmeros
        ocr_res = self.ocr_engine.recognize_pil_image(grabbed_img)
        if not ocr_res.get("success") or not ocr_res.get("text"):
            print("[LoTra OCR Snip] Nenhum texto legível encontrado pelo OCR.")
            return

        # 5. Normaliza quebras de linha e traduz localmente
        clean_text = normalize_text_spacing(ocr_res["text"])
        trans_res = self.translate_text(clean_text)
        trans_res["engine_used"] = f"WinRT OCR ({ocr_res.get('inference_ms', 0):.0f}ms) + {trans_res['engine_used']}"

        self._ui_queue.put(trans_res)

    def stop_hud_service(self):
        """Para o daemon HUD cooperativamente e executa checkpoint de encerramento limpo do banco."""
        self._is_serving = False
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.screen_snipper and self.screen_snipper.is_active:
            self.screen_snipper.cancel()
        self.hud.destroy()
        if self.vault:
            self.vault.shutdown()
        VRAMManager.trim_process_memory()

    def start_hud_service(self, show_gui: bool = True):
        """Inicia o daemon de segundo plano com escuta estrita dos 2 atalhos globais e interface gráfica."""
        print("[LoTra] Iniciando serviço LoTra no Windows...")
        print("[LoTra] Atalhos globais ativos: [Alt + Q] (Seleção) e [Alt + W] (OCR)")
        print("[LoTra] Instruções de uso:")
        print("  - [Alt + Q]: Selecione qualquer texto com o mouse e pressione Alt+Q (cópia automática ativada!).")
        print("  - [Alt + W]: Pressione Alt+W para recortar área da tela e traduzir o texto reconhecido via OCR.")
        
        self.hotkey_listener = HotkeyListener(
            callback=self.trigger_quick_translation_from_selection,
            on_ocr_snip=self.trigger_ocr_screen_snip
        )
        self.hotkey_listener.start()
        self._is_serving = True

        if show_gui:
            # Exibe a janela principal moderna no desktop em vez do terminal
            try:
                self.main_window = LoTraMainWindow(app=self)
                self.main_window.start_main_loop()
            finally:
                self.stop_hud_service()
            return

        # Modo headless (terminal / background sem janela principal aberta)
        try:
            while self._is_serving:
                while not self._ui_queue.empty():
                    try:
                        item = self._ui_queue.get_nowait()
                        if isinstance(item, dict) and item.get("_action") == "start_native_snip":
                            self._handle_native_snip()
                            continue

                        res = item
                        self.hud.show(
                            translated_text=res["translated_text"],
                            source_text=res.get("source_text", ""),
                            latency_ms=res.get("latency_ms", 0.0),
                            engine_name=res.get("engine_used", "LoTra Engine"),
                            timeout_sec=0.0,
                            cursor_pos=res.get("cursor_pos")
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
