"""
Bateria de Testes Unitários dos 10 Bugs e Melhorias da Interface Gráfica do LoTra:
1. Bug 1: Espaçamento de tradução, normalização de PDFs e prevenção de frases coladas.
2. Bug 2: Vocabulário offline abrangente e erradicação de palavras residuais em inglês.
3. Bug 3: Fechamento automático ao clicar fora da box (dismiss outside box).
4. Bug 4: Auto-dismiss desligado por padrão (permanece na tela sem fechar após poucos segundos).
5. Bug 5: Inicialização com UI visível na área de trabalho em vez de processo oculto.
6. Bug 6: Single-Instance Mutex (bloqueio rigoroso de múltiplos processos LoTra.exe acumulados).
7. Bug 7: Interface gráfica interativa (substituição do terminal por GUI moderna).
8. Bug 8: Ícone e logo gerados a partir do Meio.dc.html com múltiplas resoluções.
9. Bug 9: Consistência cromática com a nova logo (paleta teal #0f5c6e e creme #f6f1e8).
10. Bug 10: Execução automatizada e validação de cobertura dos testes.
"""

import os
import sys
import time
import unittest
import tkinter as tk
from pathlib import Path
from PIL import Image

# Adiciona diretórios ao path
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from platform_core import SingleInstanceGuard, get_app_data_dir
from hud_tooltip import normalize_text_spacing, HUDTooltip, get_windows_clipboard_text, set_windows_clipboard_text
from translation_engine import OfflineContextTranslator, TranslationPipeline
from document_context_vault import DocumentContextVault
from resource_utils import get_resource_path
from ui_window import LoTraMainWindow

class TestLoTraBugsAndUI(unittest.TestCase):
    """Testes unitários dedicados aos 10 pontos auditados."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_vault.db"
        cls.vault = DocumentContextVault(db_path=str(cls.db_path))
        cls.pipeline = TranslationPipeline(vault=cls.vault)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'vault'):
            cls.vault.shutdown()
        if hasattr(cls, 'temp_dir'):
            cls.temp_dir.cleanup()

    def test_bug1_text_spacing_and_glued_phrases(self):
        """Valida que quebras de linha de PDFs e pontuações coladas são normalizadas sem colar palavras."""
        # 1. Pontuação colada em letra (ex: erro comum de OCR/clipboard: "sentence.Next")
        raw_glued = "This is the first sentence.Second sentence follows immediately:another clause."
        norm = normalize_text_spacing(raw_glued)
        self.assertIn("sentence. Second", norm)
        self.assertIn("immediately: another", norm)

        # 2. Hifenização de fim de linha de coluna de PDF
        pdf_hyphen = "Recent advances in inter-\noperability and over-\nreliance are notable."
        norm_pdf = normalize_text_spacing(pdf_hyphen)
        self.assertIn("interoperability", norm_pdf)
        self.assertIn("overreliance", norm_pdf)
        self.assertNotIn("inter-\n", norm_pdf)

        # 3. Quebras duras de linha concatenadas em fluxo contínuo
        multi_line = "First line of thought\ncontinues smoothly on the second line."
        norm_flow = normalize_text_spacing(multi_line)
        self.assertEqual(norm_flow, "First line of thought continues smoothly on the second line.")

    def test_bug2_no_untranslated_english_words(self):
        """Valida que o tradutor offline traduz palavras comuns, verbos e termos sem deixar vocabulário em inglês."""
        test_phrases = [
            ("The study shows that the system achieves high accuracy.", ["study", "shows", "system", "achieves", "accuracy"]),
            ("We evaluated a new approach to reduce latency.", ["evaluated", "approach", "reduce", "latency"]),
            ("The author proposed a simple solution for the user.", ["author", "proposed", "solution", "user"])
        ]

        for text, english_keywords in test_phrases:
            translated = OfflineContextTranslator.translate(text)
            self.assertTrue(len(translated) > 0)
            # Verifica que as palavras-chave em inglês foram substituídas para português
            for kw in english_keywords:
                self.assertNotIn(f" {kw} ", f" {translated.lower()} ", 
                                 f"Palavra em inglês '{kw}' não foi traduzida na frase: '{translated}'")

    def test_bug3_click_outside_box_dismiss_mechanism(self):
        """Valida que o HUDTooltip possui mecanismo de fechamento ao clicar fora da janela."""
        hud = HUDTooltip()
        hud.show("Texto de teste para validação de clique fora", timeout_sec=0.0)
        self.assertTrue(hud._is_active)
        self.assertIsNotNone(hud._window)
        self.assertIsNotNone(hud._outside_poll_job)

        # Invoca dismiss e valida limpeza imediata
        hud.dismiss()
        self.assertFalse(hud._is_active)
        self.assertIsNone(hud._window)
        self.assertIsNone(hud._outside_poll_job)
        hud.destroy()

    def test_bug4_no_auto_dismiss_timeout_zero(self):
        """Valida que por padrão timeout_sec é 0.0 (sem fechamento forçado após alguns segundos)."""
        hud = HUDTooltip()
        hud.show("Texto persistente enquanto o usuário lê", timeout_sec=0.0)
        # Quando timeout_sec é 0.0, _close_timer não deve ser agendado
        self.assertIsNone(hud._close_timer, "Auto-dismiss timer não deve ser agendado quando timeout_sec=0.0")
        hud.dismiss()
        hud.destroy()

    def test_bug5_and_bug7_ui_window_initialization(self):
        """Valida construção e integridade da janela gráfica Tkinter principal que substitui o terminal."""
        class MockApp:
            def __init__(self):
                self._ui_queue = None
                self._is_serving = True
            def profile_hardware(self):
                return {
                    "cpu_cores": 8,
                    "avail_ram_gb": 12.0,
                    "gpu_name": "Radeon Graphics",
                    "recommended_tier": "small"
                }
            def translate_text(self, txt):
                return {
                    "source_text": txt,
                    "translated_text": "Texto traduzido com sucesso.",
                    "latency_ms": 15.2,
                    "engine_used": "LoTra Test Engine"
                }
            def stop_hud_service(self):
                pass

        mock_app = MockApp()
        main_win = LoTraMainWindow(app=mock_app)
        self.assertIsNotNone(main_win.root)
        self.assertEqual(main_win.root.title(), "LoTra - Tradução e Leitura Fluida")

        # Testa tradução interativa dentro da UI
        main_win.txt_input.delete("1.0", "end")
        main_win.txt_input.insert("1.0", "Hello world")
        main_win._do_manual_translate()

        res_out = main_win.txt_output.get("1.0", "end").strip()
        self.assertEqual(res_out, "Texto traduzido com sucesso.")
        self.assertIn("15.2ms", main_win.lbl_stats.cget("text"))

        main_win.root.destroy()

    def test_bug6_single_instance_mutex_guard(self):
        """Valida que SingleInstanceGuard impede a criação de múltiplos processos LoTra.exe em paralelo."""
        test_mutex_name = f"LoTra_UnitTest_Mutex_{os.getpid()}_{int(time.time())}"
        guard1 = SingleInstanceGuard(mutex_name=test_mutex_name)
        guard2 = SingleInstanceGuard(mutex_name=test_mutex_name)

        try:
            # Primeira instância adquire o mutex com sucesso
            acquired_1 = guard1.acquire()
            self.assertTrue(acquired_1, "A primeira instância deve adquirir o mutex primário.")

            if sys.platform == "win32":
                # Segunda instância tenta adquirir o mesmo mutex nomeado e deve ser rejeitada
                acquired_2 = guard2.acquire()
                self.assertFalse(acquired_2, "A segunda instância deve ser rejeitada para evitar múltiplos processos.")
        finally:
            guard1.release()
            guard2.release()

    def test_bug8_and_bug9_icon_and_logo_consistency(self):
        """Valida o ícone da Lontra, resoluções e conformidade cromática com Meio.dc.html (#0f5c6e)."""
        ico_path = get_resource_path("assets/lotra.ico")
        png_path = get_resource_path("assets/lotra.png")

        self.assertTrue(ico_path.exists(), f"Arquivo de ícone {ico_path} deve existir.")
        self.assertTrue(png_path.exists(), f"Arquivo de logo PNG {png_path} deve existir.")

        # Inspeciona dimensões do PNG oficial
        with Image.open(png_path) as img:
            self.assertEqual(img.size, (512, 512))
            # Converte para RGB para amostrar a cor predominante do balão de fala
            rgb_img = img.convert("RGBA")
            # Amostra um pixel dentro do balão teal (ex: x=100, y=100 em viewBox)
            # Escala 512/120: pixel (250, 100) está certamente dentro do balão
            r, g, b, a = rgb_img.getpixel((250, 80))
            # Cor teal esperada: #0f5c6e -> R=15 (0x0F), G=92 (0x5C), B=110 (0x6E)
            self.assertTrue(a > 200, "Pixel amostrado deve ser opaco.")
            self.assertAlmostEqual(r, 15, delta=18, msg="Componente R deve coincidir com #0f5c6e")
            self.assertAlmostEqual(g, 92, delta=18, msg="Componente G deve coincidir com #0f5c6e")
            self.assertAlmostEqual(b, 110, delta=18, msg="Componente B deve coincidir com #0f5c6e")

    def test_anti_hallucination_and_repetition_loop_detection(self):
        """Valida a rejeição imediata de loops repetitivos e meta-respostas de recusa da LLM."""
        pipeline = TranslationPipeline()
        
        # 1. Simula resposta alucinada repetitiva reportada pelo usuário
        repetitive_hallucination = (
            "O texto fornecido está em inglês e não está relacionado diretamente à categoria de texto principal que você está solicitando. "
            "Para traduzir o texto para o português brasileiro, precisamos entender o contexto e a ideia principal. No entanto, o texto fornecido não está relacionado diretamente à categoria de texto principal que você está solicitando. "
            "Para traduzir o texto para o português brasileiro, precisamos entender o contexto e a ideia principal. No entanto, o texto fornecido não está relacionado diretamente à categoria de texto principal que você está solicitando."
        )
        self.assertFalse(pipeline._is_valid_translation(repetitive_hallucination), "O validador DEVE rejeitar loops e meta-comentários.")

        # 2. Resposta legítima deve ser aceita
        clean_translation = "Os sistemas de interação humano-IA são tipicamente projetados para apoiar diretamente as tarefas humanas."
        self.assertTrue(pipeline._is_valid_translation(clean_translation), "Traduções legítimas devem ser aceitas normalmente.")

    def test_llm_streaming_and_latency_optimizations(self):
        """Valida as otimizações das Opções 1 e 2: streaming de tokens, dynamic num_predict e HUD progressivo."""
        hud = HUDTooltip()
        
        # 1. Inicia o streaming do HUD e verifica estado inicial
        hud.start_stream(cursor_pos=(500, 400))
        self.assertTrue(hud._is_active)
        self.assertTrue(hud._is_streaming)
        self.assertEqual(hud._current_text, "...")

        # 2. Emite chunks de tokens progressivos
        hud.update_stream("A", "A")
        self.assertEqual(hud._current_text, "A")
        hud.update_stream(" separação", "A separação")
        self.assertEqual(hud._current_text, "A separação")
        hud.update_stream(" de poderes", "A separação de poderes")
        self.assertEqual(hud._current_text, "A separação de poderes")

        # 3. Finaliza o streaming
        hud.finish_stream("A separação de poderes opera como um sistema de freios e contrapesos.", latency_ms=45.0, engine_name="Ollama (qwen2.5:1.5b)")
        self.assertFalse(hud._is_streaming)
        self.assertTrue(hud._is_active)
        self.assertIn("separação de poderes", hud._current_text)

        hud.dismiss()
        self.assertFalse(hud._is_active)

        # 4. Valida pipeline de tradução com callback de streaming
        received_tokens = []
        def stream_recorder(delta, full_so_far):
            received_tokens.append(delta)

        # Usando texto para validar que o callback de streaming recebe tokens da LLM ou fallback
        res = self.pipeline.translate_text("hello world", stream_callback=stream_recorder)
        self.assertTrue(len(received_tokens) > 0, "O callback de streaming deve receber o texto traduzido.")
        self.assertEqual(res["translated_text"].lower().strip("!."), "olá mundo")

    def test_modern_web_ui_dashboard_features(self):
        """Valida novos componentes de UI moderna web: tabs segmentadas, chips de amostra, contador de chars e cópia."""
        class MockApp:
            def __init__(self):
                self._ui_queue = None
                self._is_serving = True
            def profile_hardware(self):
                return {
                    "cpu_cores": 8,
                    "avail_ram_gb": 12.0,
                    "total_ram_gb": 16.0,
                    "gpu_name": "Radeon Graphics",
                    "gpu_backend": "DirectML",
                    "recommended_tier": "small",
                    "recommended_model": "qwen2.5:1.5b"
                }
            def translate_text(self, txt, **kwargs):
                return {
                    "source_text": txt,
                    "translated_text": f"Traduzido: {txt}",
                    "latency_ms": 12.0,
                    "engine_used": "LoTra Web Engine"
                }
            def run_self_test(self):
                return {"all_passed": True, "subsystems": {}}
            def stop_hud_service(self):
                pass

        mock_app = MockApp()
        win = LoTraMainWindow(app=mock_app)
        try:
            # 1. Comutação de abas
            self.assertEqual(win.current_tab, "translate")
            win._switch_tab("history")
            self.assertEqual(win.current_tab, "history")
            win._switch_tab("hardware")
            self.assertEqual(win.current_tab, "hardware")
            win._switch_tab("translate")
            self.assertEqual(win.current_tab, "translate")

            # 2. Contador de caracteres e palavras
            win._set_input_text("Hello brave new world")
            self.assertIn("21 caracteres", win.lbl_char_count.cget("text"))
            self.assertIn("4 palavras", win.lbl_char_count.cget("text"))

            # 3. Teste de tradução e cópia
            win._do_manual_translate()
            self.assertIn("Traduzido: Hello brave new world", win.txt_output.get("1.0", "end"))
            win._copy_output_to_clipboard()
            self.assertEqual(win.btn_copy.cget("text").strip(), "✓ Copiado!")

            # 4. Execução de self-test pela UI
            win._run_gui_self_test()
            self.assertIn("100%", win.lbl_selftest_res.cget("text"))
        finally:
            win.root.destroy()

    def test_placeholder_lifecycle_and_character_counts(self):
        """Valida ciclo de vida do placeholder: foco, perda de foco, limpeza e contagem de caracteres."""
        class MockApp:
            def __init__(self):
                self._ui_queue = None
                self._is_serving = True
            def profile_hardware(self):
                return {"cpu_cores": 4, "avail_ram_gb": 8.0, "total_ram_gb": 16.0, "gpu_name": "Mock", "gpu_backend": "CPU"}
            def translate_text(self, txt, **kwargs):
                return {"source_text": txt, "translated_text": f"OK: {txt}", "latency_ms": 5.0, "engine_used": "Mock"}
            def run_self_test(self):
                return {"all_passed": True, "subsystems": {}}
            def stop_hud_service(self):
                pass

        win = LoTraMainWindow(app=MockApp())
        try:
            # 1. Limpa campos: placeholder deve estar presente e contador deve mostrar 0
            win._clear_fields()
            self.assertEqual(win.txt_input.get("1.0", "end").strip(), win._placeholder_text)
            self.assertEqual(win.txt_input.cget("fg"), win.c_text_placeholder)
            self.assertIn("0 caracteres", win.lbl_char_count.cget("text"))
            self.assertIn("0 palavras", win.lbl_char_count.cget("text"))

            # 2. Focus In deve limpar o placeholder se presente
            win._on_input_focus_in()
            self.assertEqual(win.txt_input.get("1.0", "end").strip(), "")
            self.assertEqual(win.txt_input.cget("fg"), win.c_text)

            # 3. Focus Out sem texto digitado deve restaurar o placeholder
            win._on_input_focus_out()
            self.assertEqual(win.txt_input.get("1.0", "end").strip(), win._placeholder_text)
            self.assertEqual(win.txt_input.cget("fg"), win.c_text_placeholder)
            self.assertIn("0 caracteres", win.lbl_char_count.cget("text"))

            # 4. Digitação de texto real atualiza contador
            win._on_input_focus_in()
            win.txt_input.insert("1.0", "Artificial Intelligence and Machine Learning")
            win._on_input_changed()
            self.assertEqual(win.txt_input.cget("fg"), win.c_text)
            self.assertIn("44 caracteres", win.lbl_char_count.cget("text"))
            self.assertIn("5 palavras", win.lbl_char_count.cget("text"))

            # 5. Focus Out com texto real mantém o texto e o contador
            win._on_input_focus_out()
            self.assertEqual(win.txt_input.get("1.0", "end").strip(), "Artificial Intelligence and Machine Learning")
            self.assertIn("44 caracteres", win.lbl_char_count.cget("text"))
        finally:
            win.root.destroy()

    def test_untruncated_history_retrieval_and_double_click(self):
        """Valida que textos longos no histórico (> 60 chars) não são truncados ao carregar no tradutor ou copiar."""
        import tempfile
        from document_context_vault import DocumentContextVault

        temp_db = tempfile.mktemp(suffix=".db")
        vault = DocumentContextVault(db_path=temp_db, enable_privacy=False)

        long_src = "Superconducting quantum circuits require cryogenic attenuation stages to suppress thermal photons and crosstalk between readout lines."
        long_trans = "Circuitos quânticos supercondutores requerem estágios de atenuação criogênica para suprimir fótons térmicos e diafonia entre linhas de leitura."
        self.assertGreater(len(long_src), 100)
        self.assertGreater(len(long_trans), 120)

        vault.store_cache("test_doc", 1, long_src, "", long_trans, "test_model", 8.5)

        class MockAppWithVault:
            def __init__(self):
                self._ui_queue = None
                self._is_serving = True
                self.vault = vault
            def profile_hardware(self):
                return {"cpu_cores": 8, "avail_ram_gb": 16.0, "total_ram_gb": 32.0, "gpu_name": "DirectML", "gpu_backend": "DirectML"}
            def translate_text(self, txt, **kwargs):
                return {"source_text": txt, "translated_text": f"Trad: {txt}", "latency_ms": 10.0, "engine_used": "Test"}
            def run_self_test(self):
                return {"all_passed": True, "subsystems": {}}
            def stop_hud_service(self):
                pass

        win = LoTraMainWindow(app=MockAppWithVault())
        try:
            win._switch_tab("history")
            children = win.tree_history.get_children()
            self.assertEqual(len(children), 1)
            item_id = children[0]

            # Valida carregamento no tradutor com texto 100% completo (sem truncamento a 60 chars)
            win.tree_history.selection_set(item_id)
            win._load_selected_history_item()
            self.assertEqual(win.current_tab, "translate")
            loaded_input = win.txt_input.get("1.0", "end").strip()
            loaded_output = win.txt_output.get("1.0", "end").strip()

            self.assertEqual(loaded_input, long_src)
            self.assertEqual(loaded_output, long_trans)

            # Valida cópia para o clipboard com texto completo
            win._copy_selected_history_item()
            copied = get_windows_clipboard_text()
            self.assertEqual(copied, long_trans)
        finally:
            win.root.destroy()
            vault.shutdown()
            try:
                import os
                os.remove(temp_db)
            except Exception:
                pass

    def test_non_blocking_async_translate_and_selftest(self):
        """Valida que _do_manual_translate e _run_gui_self_test com async_mode=True executam em background sem travar UI."""
        class MockAppAsync:
            def __init__(self):
                self._ui_queue = None
                self._is_serving = True
            def profile_hardware(self):
                return {"cpu_cores": 8, "avail_ram_gb": 16.0, "total_ram_gb": 32.0, "gpu_name": "GPU", "gpu_backend": "DirectML"}
            def translate_text(self, txt, stream_callback=None, **kwargs):
                time.sleep(0.08)
                if stream_callback:
                    stream_callback("Trad", "Trad")
                    stream_callback("uzido!", "Traduzido!")
                return {"source_text": txt, "translated_text": f"Async: {txt}", "latency_ms": 80.0, "engine_used": "MockAsync"}
            def run_self_test(self):
                time.sleep(0.08)
                return {"all_passed": True, "subsystems": {"test": {"status": "PASS"}}}
            def stop_hud_service(self):
                pass

        win = LoTraMainWindow(app=MockAppAsync())
        try:
            # 1. Tradução assíncrona não trava UI
            win._set_input_text("Testing async execution")
            win._do_manual_translate(async_mode=True)
            self.assertTrue(win._is_translating)
            self.assertEqual(win.btn_translate.cget("state"), tk.DISABLED)

            # Processa eventos e aguarda conclusão da thread de background
            deadline = time.perf_counter() + 3.0
            while win._is_translating and time.perf_counter() < deadline:
                win.root.update()
                time.sleep(0.02)

            self.assertFalse(win._is_translating)
            self.assertEqual(win.btn_translate.cget("state"), tk.NORMAL)
            self.assertIn("Async: Testing async execution", win.txt_output.get("1.0", "end"))

            # 2. Self-test assíncrono não trava UI
            win._run_gui_self_test(async_mode=True)
            self.assertTrue(win._is_running_selftest)
            self.assertEqual(win.btn_run_selftest.cget("state"), tk.DISABLED)

            deadline = time.perf_counter() + 3.0
            while win._is_running_selftest and time.perf_counter() < deadline:
                win.root.update()
                time.sleep(0.02)

            self.assertFalse(win._is_running_selftest)
            self.assertEqual(win.btn_run_selftest.cget("state"), tk.NORMAL)
            self.assertIn("100%", win.lbl_selftest_res.cget("text"))
        finally:
            win.root.destroy()

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLoTraBugsAndUI)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return res.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
