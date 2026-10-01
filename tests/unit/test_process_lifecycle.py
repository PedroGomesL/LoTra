"""
Testes Unitários de Gerenciamento de Processos e Ciclo de Vida:
1. Windows Job Objects (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE).
2. LocalNeuralEngineManager (Detecção de binário, verificação de servidor, VRAM unload).
3. Encerramento seguro sem vazamento de processos órfãos ou memória RAM/VRAM.
"""

import sys
import time
import subprocess
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from platform_core import (
    WindowsJobObject,
    LocalNeuralEngineManager,
    get_neural_engine_manager,
    VRAMManager
)
from app import LoTraApp


class TestProcessLifecycleAndJobObjects(unittest.TestCase):
    """Testa o gerenciamento de ciclo de vida com Windows Job Objects e Neural Engine."""

    def test_job_object_kill_on_close(self):
        """Valida que processos associados ao Job Object são encerrados no fechamento do handle."""
        job = WindowsJobObject()
        if sys.platform != "win32":
            self.skipTest("Windows Job Objects são específicos para Win32")

        self.assertTrue(job._is_active, "Job Object deve estar ativo no Windows")
        self.assertIsNotNone(job.handle)

        # Lança subprocesso ping que rodaria por vários segundos
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        proc = subprocess.Popen(
            ["ping", "-n", "10", "127.0.0.1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

        assigned = job.assign_process(proc)
        self.assertTrue(assigned, "Processo deve ser associado ao Job Object com sucesso")

        # Fecha o Job Object -> Kernel do Windows deve encerrar o processo filho
        job.close()
        self.assertFalse(job._is_active)
        self.assertIsNone(job.handle)

        time.sleep(0.3)
        poll_res = proc.poll()
        self.assertIsNotNone(poll_res, "Processo filho deve ter sido encerrado pelo Job Object")

    def test_neural_engine_manager_status_and_discovery(self):
        """Valida detecção de binário, verificação de status e listagem de modelos."""
        mgr = get_neural_engine_manager()
        self.assertIsInstance(mgr, LocalNeuralEngineManager)

        installed = mgr.is_installed()
        self.assertIsInstance(installed, bool)

        listening = mgr.is_server_listening()
        self.assertIsInstance(listening, bool)

        status = mgr.get_status()
        self.assertIn("installed", status)
        self.assertIn("running", status)
        self.assertIn("display_text", status)
        self.assertIn("neural_enabled", status)

        # Valida que o display_text é seguro para encoding de terminal
        disp = status["display_text"]
        self.assertIsInstance(disp, str)
        self.assertTrue(any(tag in disp for tag in ["[ATIVO]", "[INATIVO]", "[OFFLINE]"]))

    def test_neural_engine_enable_toggle(self):
        """Valida a capacidade de ligar e desligar a inferência neural cooperativamente."""
        mgr = get_neural_engine_manager()
        orig = mgr.is_neural_enabled()
        try:
            mgr.set_neural_enabled(False)
            self.assertFalse(mgr.is_neural_enabled())
            mgr.set_neural_enabled(True)
            self.assertTrue(mgr.is_neural_enabled())
        finally:
            mgr.set_neural_enabled(orig)

    def test_vram_manager_trim_memory(self):
        """Valida que o trim_process_memory e VRAMManager não disparam exceções."""
        VRAMManager.trim_process_memory()
        res = VRAMManager.unload_ollama_models(ollama_url="http://127.0.0.1:11434")
        self.assertIsInstance(res, bool)

    def test_app_neural_engine_facade(self):
        """Valida métodos da fachada LoTraApp para controle do motor neural."""
        app = LoTraApp()
        st = app.get_neural_engine_status()
        self.assertIsInstance(st, dict)
        self.assertIn("running", st)

        # Teste de parada cooperativa e trim
        stop_res = app.stop_neural_engine()
        self.assertTrue(stop_res.get("success", False))

        # Diagnóstico integrado
        diag = app.run_self_test()
        self.assertTrue(diag["all_passed"])
        self.assertIn("neural_engine_lifecycle", diag["subsystems"])
        self.assertEqual(diag["subsystems"]["neural_engine_lifecycle"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
