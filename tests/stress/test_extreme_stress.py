"""
Bateria de Testes Extremos de Estresse, Concorrência e Casos de Borda do LoTra:
1. test_rapid_concurrent_alt_q_triggers: 50 disparos simultâneos/rápidos de Alt+Q, prevenção de deadlocks e descarte de epochs obsoletos.
2. test_massive_text_input: Entrada massiva (> 100.000 caracteres), estabilidade de memória, geometria e preservação de clipboard completo.
3. test_corrupted_unicode_and_null_bytes: Caracteres nulos, surrogates quebrados, caracteres de controle e RTL sem UnicodeEncodeError.
4. test_clipboard_contention_and_fallback: Contenção de clipboard, simulação de locks concorrentes e buffer de fallback resiliente.
5. test_simulated_ollama_drops_and_stream_interruptions: Falha de conexão/timeout/JSON corrompido no meio do streaming com fallback 100% offline.
6. test_concurrent_alt_q_and_alt_w_triggers: Disparo simultâneo de Alt+Q (seleção) e Alt+W (OCR) sem colisão de estado.
7. test_hotkey_listener_lifecycle_and_fallback: Inicialização, ciclo de vida e ativação de fallback por polling sem deadlocks.
8. test_vault_concurrency_stress: 20 threads concorrentes com centenas de leituras/escritas simultâneas no cofre SQLite.
"""

import sys
import time
import queue
import urllib.error
import threading
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ajusta sys.path
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import LoTraApp
from hud_tooltip import (
    normalize_text_spacing, 
    HUDTooltip, 
    set_windows_clipboard_text, 
    get_windows_clipboard_text,
    simulate_copy_selection,
    HotkeyListener,
    _CLIPBOARD_FALLBACK_BUFFER
)
from translation_engine import TranslationPipeline, OfflineContextTranslator
from document_context_vault import DocumentContextVault
from privacy_vault import VaultProtector


class TestLoTraExtremeStress(unittest.TestCase):
    """Testes extremos de robustez arquitetural e concorrência."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "stress_vault.db"
        cls.vault = DocumentContextVault(db_path=str(cls.db_path))
        cls.app = LoTraApp()
        cls.app.vault = cls.vault

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "vault"):
            cls.vault.shutdown()
        if hasattr(cls, "app"):
            cls.app.stop_hud_service()
        if hasattr(cls, "temp_dir"):
            cls.temp_dir.cleanup()

    def test_1_rapid_concurrent_alt_q_triggers(self):
        """Dispara 50 traduções simultâneas/rápidas e valida descarte de epochs anteriores sem deadlock."""
        num_triggers = 50
        errors = []
        finished_ids = []

        def trigger_worker(worker_id):
            try:
                sample_text = f"Recent advances in generative ai number {worker_id}"
                self.app._dispatch_translation(sample_text)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=trigger_worker, args=(i,)) for i in range(num_triggers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        self.assertEqual(len(errors), 0, f"Erros durante 50 disparos simultâneos: {errors}")
        self.assertGreaterEqual(self.app._active_translation_id, num_triggers)

        # Drena a fila e valida que itens obsoletos foram filtrados ou estão ordenados
        consumed = 0
        latest_seen = -1
        while not self.app._ui_queue.empty():
            item = self.app._ui_queue.get_nowait()
            consumed += 1
            if isinstance(item, dict) and "trans_id" in item:
                latest_seen = max(latest_seen, item["trans_id"])

        self.assertGreater(consumed, 0)
        self.assertEqual(latest_seen, self.app._active_translation_id)

    def test_2_massive_text_input(self):
        """Entrada massiva de 120.000 caracteres (> 100k) sem travamentos, estouro de memória ou tela."""
        huge_text = ("Artificial intelligence and machine learning algorithms continue to evolve. " * 1500)
        self.assertGreater(len(huge_text), 100000)

        # 1. Normalização de espaçamento em texto massivo
        t0 = time.perf_counter()
        normalized = normalize_text_spacing(huge_text)
        norm_elapsed = time.perf_counter() - t0
        self.assertLess(norm_elapsed, 1.5, f"Normalização demorou demais: {norm_elapsed:.2f}s")
        self.assertGreater(len(normalized), 90000)

        # 2. Geometria do HUD Tooltip com texto massivo
        hud = HUDTooltip()
        hud._cursor_pos = (500, 400)
        hud._mon_left = 0
        hud._mon_top = 0
        hud._mon_right = 1920
        hud._mon_bottom = 1080

        # Cria Toplevel mockado para validar _update_geometry
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        hud.set_root(root)
        try:
            hud.start_stream(cursor_pos=(500, 400))
            hud._update_geometry(normalized)
            # Valida que o texto exibido no Label foi truncado para estabilidade do HUD
            lbl_text = hud._trans_label.cget("text")
            self.assertLessEqual(len(lbl_text), 4500)
            self.assertIn("Tradução truncada para exibição no HUD", lbl_text)

            # Valida que o texto COMPLETO (120k chars) foi preservado para cópia no clique
            self.assertEqual(hud._full_text, normalized)

            # Simula clique e verifica gravação íntegra do texto massivo
            hud.finish_stream(normalized)
            set_windows_clipboard_text(hud._full_text)
            clip_res = get_windows_clipboard_text()
            self.assertEqual(len(clip_res), len(normalized))
        finally:
            hud.dismiss()
            root.destroy()

    def test_3_corrupted_unicode_and_null_bytes(self):
        """Texto com bytes nulos, controle e surrogates quebrados processado sem UnicodeEncodeError."""
        corrupted_samples = [
            "Normal text with \x00 null bytes and \x07 bell and \x1b escape",
            "Broken surrogate \ud800 in the middle of \udfff sentence",
            "Mixed RTL \u200f and zero-width \u200b\u200c characters: artificial intelligence",
            "Multi-byte emoji with corrupted trailing byte: \U0001F600\x00\x01\x02 test"
        ]

        for sample in corrupted_samples:
            # 1. normalize_text_spacing não pode lançar exceção
            cleaned = normalize_text_spacing(sample)
            self.assertNotIn("\x00", cleaned)
            self.assertNotIn("\x07", cleaned)

            # 2. Cópia e leitura do clipboard
            set_windows_clipboard_text(cleaned)
            clip = get_windows_clipboard_text()
            self.assertIsInstance(clip, str)

            # 3. Cache no DocumentContextVault não pode falhar com UnicodeEncodeError
            self.vault.store_cache(
                doc_hash="corrupt_test",
                page_num=1,
                source_text=cleaned,
                context_used="",
                translated_text="Tradução sanitizada com sucesso",
                model_id="test_model",
                latency_ms=1.0
            )
            retrieved = self.vault.lookup_cache("corrupt_test", cleaned, "test_model")
            self.assertEqual(retrieved, "Tradução sanitizada com sucesso")

            # 4. VaultProtector criptografia DPAPI/AES com surrogates
            enc = VaultProtector.encrypt_text(sample)
            dec = VaultProtector.decrypt_text(enc)
            self.assertIsInstance(dec, str)

    def test_4_clipboard_contention_and_fallback(self):
        """Simula falhas do Win32 OpenClipboard e valida o fallback buffer resiliente."""
        test_val = "Resilient LoTra Clipboard Content 2026"
        set_windows_clipboard_text(test_val)

        # Simula falha total do OpenClipboard (ex: estação bloqueada ou outro app travando clipboard)
        with patch("ctypes.windll.user32.OpenClipboard", return_value=False):
            # Leitura deve retornar o buffer resiliente em vez de quebrar ou retornar vazio
            res = get_windows_clipboard_text()
            self.assertEqual(res, test_val)

            # Escrita deve retornar True gravando no buffer de fallback
            write_res = set_windows_clipboard_text("Updated Fallback Text")
            self.assertTrue(write_res)
            self.assertEqual(get_windows_clipboard_text(), "Updated Fallback Text")

    def test_5_simulated_ollama_drops_and_stream_interruptions(self):
        """Simula queda de conexão ou JSON quebrado no Ollama durante streaming com fallback 100% offline."""
        pipeline = TranslationPipeline(vault=self.vault)

        # Simula Ollama online mas lançando erro de conexão durante a requisição de streaming
        with patch.object(pipeline, "_is_ollama_available", return_value=True), \
             patch.object(pipeline, "_get_available_ollama_model", return_value="qwen2.5:1.5b"), \
             patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection reset by peer")):

            chunks_received = []
            def stream_cb(delta, full):
                chunks_received.append(delta)

            # Deve cair graciosamente para o tradutor offline local sem levantar exceção
            res = pipeline.translate_text(
                "Recent advances in artificial intelligence continue to evolve.",
                doc_hash="stream_drop_test",
                stream_callback=stream_cb
            )

            self.assertIsNotNone(res)
            self.assertTrue(res["translated_text"])
            self.assertIn("inteligência artificial", res["translated_text"].lower())
            self.assertIn("Offline", res["engine_used"])

    def test_6_concurrent_alt_q_and_alt_w_triggers(self):
        """Simula disparos intercalados e quase simultâneos de Alt+Q e Alt+W sem colisão."""
        self.app._is_serving = True
        q_count = 6
        w_count = 6

        def q_worker():
            for i in range(q_count):
                self.app._dispatch_translation(f"Artificial intelligence {i}")

        def w_worker():
            for _ in range(w_count):
                self.app._ui_queue.put({"_action": "start_native_snip"})

        t_q = threading.Thread(target=q_worker)
        t_w = threading.Thread(target=w_worker)
        t_q.start()
        t_w.start()
        t_q.join(timeout=10.0)
        t_w.join(timeout=10.0)

        # Valida que a fila processou tanto ações de recorte quanto de tradução
        has_snip_action = False
        has_trans_action = False

        while not self.app._ui_queue.empty():
            item = self.app._ui_queue.get_nowait()
            if isinstance(item, dict):
                if item.get("_action") == "start_native_snip":
                    has_snip_action = True
                elif "translated_text" in item or item.get("_action") in ("stream_start", "stream_chunk", "stream_end"):
                    has_trans_action = True

        self.assertTrue(has_snip_action, "Ações de recorte (Alt+W) devem ser registradas na fila.")
        self.assertTrue(has_trans_action, "Ações de tradução (Alt+Q) devem ser registradas na fila.")

    def test_7_hotkey_listener_lifecycle_and_fallback(self):
        """Valida que o HotkeyListener inicia, para e lida com falha de RegisterHotKey sem deadlocks."""
        called_q = []
        called_w = []

        def on_q():
            called_q.append(True)

        def on_w():
            called_w.append(True)

        listener = HotkeyListener(callback=on_q, on_ocr_snip=on_w)

        # 1. Simula RegisterHotKey falhando (retornando False) para ativar branch de polling resiliente
        with patch("ctypes.windll.user32.RegisterHotKey", return_value=False), \
             patch("ctypes.windll.user32.UnregisterHotKey", return_value=True):
            listener.start()
            self.assertTrue(listener.running)
            time.sleep(0.08)
            listener.stop()
            self.assertFalse(listener.running)

    def test_8_vault_concurrency_stress(self):
        """20 threads realizando 200 operações concorrentes de leitura e escrita no cofre SQLite (ACID)."""
        num_threads = 20
        ops_per_thread = 10
        errors = []

        def vault_worker(t_id):
            try:
                for op in range(ops_per_thread):
                    key = f"key_{t_id}_{op}"
                    self.vault.store_cache(
                        doc_hash="stress_concurrent_doc",
                        page_num=1,
                        source_text=key,
                        context_used="concurrent context",
                        translated_text=f"Tradução de {key}",
                        model_id="stress_model",
                        latency_ms=0.5
                    )
                    cached = self.vault.lookup_cache("stress_concurrent_doc", key, "stress_model")
                    if cached != f"Tradução de {key}":
                        errors.append(f"Inconsistência de cache para {key}: esperado 'Tradução de {key}', obtido '{cached}'")
            except Exception as e:
                errors.append(f"Exceção na thread {t_id}: {e}")

        threads = [threading.Thread(target=vault_worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(errors), 0, f"Erros durante estresse concorrente do cofre: {errors}")

    def test_9_alt_q_debounce_and_no_stale_clipboard_leak(self):
        """Valida que Alt+Q não traduz clipboard antigo se a seleção estiver vazia e aplica debounce em rajada."""
        # 1. Coloca texto antigo no clipboard
        old_text = "Ancient Clipboard Text From 2 Hours Ago"
        set_windows_clipboard_text(old_text)
        self.app._last_alt_q_trigger = 0.0

        # 2. Simula simulate_copy_selection retornando vazio (nenhum texto selecionado)
        notices = []
        with patch.object(self.app, "_display_hud_notice", side_effect=lambda msg: notices.append(msg)), \
             patch("app.simulate_copy_selection", return_value=""):
            self.app.trigger_quick_translation_from_selection()

            # Deve exibir aviso explicativo ao usuário em vez de traduzir o texto antigo
            self.assertEqual(len(notices), 1)
            self.assertIn("Nenhum texto selecionado", notices[0])

        # 3. Valida debounce em rajada de 10 chamadas ultra-rápidas de Alt+Q
        self.app._last_alt_q_trigger = 0.0
        call_count = [0]
        def mock_copy(*args, **kwargs):
            call_count[0] += 1
            return "Test selection"

        with patch("app.simulate_copy_selection", side_effect=mock_copy), \
             patch.object(self.app, "_dispatch_translation"):
            for _ in range(10):
                self.app.trigger_quick_translation_from_selection()
            # Devido ao debounce de hardware de 250ms, apenas a 1ª chamada é executada
            self.assertEqual(call_count[0], 1, f"Debounce falhou: esperada 1 execução, obtido {call_count[0]}")

    def test_10_clipboard_memory_safety_stress(self):
        """Executa 40 gravações e leituras rápidas para garantir ausência de memory leaks no heap Win32."""
        for i in range(40):
            payload = f"LoTra Stress Payload Cycle {i}: " + ("x" * (i * 20))
            ok = set_windows_clipboard_text(payload)
            self.assertTrue(ok)
            read_back = get_windows_clipboard_text()
            self.assertEqual(read_back, payload)

    def test_11_simulate_copy_selection_menu_masking(self):
        """Valida que as rotinas de supressão de menu e liberação de modificadores executam sem exceções."""
        from src.hud_tooltip import _force_release_all_modifiers, _suppress_menu_activation, _send_synthetic_key
        # Não deve lançar nenhuma exceção mesmo em ambiente sem foco ou headless
        _force_release_all_modifiers()
        _suppress_menu_activation()
        _send_synthetic_key(0x11, is_up=True)
        self.assertTrue(True)

    def test_12_unicode_zero_width_and_invisible_cleaner(self):
        """Valida que caracteres invisíveis (zero-width, BOM, non-breaking space, soft-hyphen) são limpos e termos do glossário identificados."""
        dirty_input = "\ufeffRecent\u00a0advances\u200b in\u200c generative\u200d ai\u00a0continue to\xad evolve."
        cleaned = normalize_text_spacing(dirty_input)
        self.assertNotIn("\ufeff", cleaned)
        self.assertNotIn("\u200b", cleaned)
        self.assertNotIn("\u200c", cleaned)
        self.assertNotIn("\u200d", cleaned)
        self.assertNotIn("\xad", cleaned)
        self.assertNotIn("\u00a0", cleaned)
        self.assertEqual(cleaned, "Recent advances in generative ai continue to evolve.")

        # Tradução com input sujo deve funcionar perfeitamente
        res = self.app.translate_text(dirty_input)
        self.assertTrue(res["translated_text"])
        self.assertIn("evoluir", res["translated_text"].lower())

    def test_13_rapid_tab_switching_and_history_loading(self):
        """Valida comutação em rajada (45x) de abas na UI moderna e carregamento de itens do histórico."""
        from ui_window import LoTraMainWindow
        import tkinter as tk

        main_win = LoTraMainWindow(app=self.app)
        try:
            # Comutação rápida entre as 3 abas sem erros
            tabs = ["translate", "history", "hardware"]
            for i in range(45):
                target = tabs[i % 3]
                main_win._switch_tab(target)
                self.assertEqual(main_win.current_tab, target)

            # Insere um registro no cofre e atualiza lista de histórico
            self.vault.store_cache("tab_test_doc", 1, "Deep Learning Architecture", "", "Arquitetura de Aprendizado Profundo", "test_model", 10.5)
            main_win._refresh_history_list()
            children = main_win.tree_history.get_children()
            self.assertGreater(len(children), 0)

            # Simula seleção e carregamento no tradutor
            main_win.tree_history.selection_set(children[0])
            main_win._load_selected_history_item()
            self.assertEqual(main_win.current_tab, "translate")
            self.assertIn("Deep Learning Architecture", main_win.txt_input.get("1.0", "end"))
        finally:
            try:
                main_win.root.destroy()
            except Exception:
                pass

    def test_14_rapid_concurrent_ocr_and_selection_switching(self):
        """Simula disparo concorrente de seleção e OCR com trans_id estrito."""
        initial_id = self.app._active_translation_id
        threads = []
        for i in range(10):
            t1 = threading.Thread(target=self.app._dispatch_translation, args=(f"Selection text {i}",))
            t2 = threading.Thread(target=self.app._ui_queue.put, args=({"_action": "stream_start", "trans_id": initial_id + i},))
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        self.assertGreater(self.app._active_translation_id, initial_id)

    def test_15_empty_and_whitespace_extreme_inputs(self):
        """Valida que entradas totalmente vazias, somente espaços ou zero-width não quebram o pipeline."""
        empty_cases = [
            "",
            "   ",
            "\n\n\t  \r\n",
            "\u200b\u200c\u200d",
            "\x00\x07\x1b",
            "   \u00a0   \u2009   "
        ]
        for ec in empty_cases:
            res = self.app.translate_text(ec)
            self.assertEqual(res["translated_text"], "")
            self.assertEqual(res["source_text"], "")
            # Normalização deve retornar string vazia limpa
            self.assertEqual(normalize_text_spacing(ec), "")

    def test_16_hud_web_features_and_mouse_debounce(self):
        """Valida novas funcionalidades web do HUD: botão de copiar rápido, status pill e debounce de clique fora."""
        hud = HUDTooltip()
        hud.show("Texto teste de overlay web moderno", "Source", latency_ms=22.5, engine_name="Qwen 2.5 1.5B")
        self.assertTrue(hud._is_active)
        self.assertIsNotNone(hud._window)
        self.assertIsNotNone(hud._status_pill)
        self.assertIsNotNone(hud._btn_copy)
        self.assertIn("Qwen", hud._status_pill.cget("text"))

        # Testa cópia pelo botão web do HUD
        target = getattr(hud, "_full_text", "") or hud._current_text
        set_windows_clipboard_text(target)
        copied = get_windows_clipboard_text()
        self.assertIn("Texto teste de overlay web moderno", copied)

        # Valida que o debounce do mouse foi inicializado
        self.assertIsInstance(hud._mouse_released_once, bool)
        hud.dismiss()
        hud.destroy()

    def test_17_compound_emoji_and_variation_selector_integrity(self):
        """Valida que emojis compostos com ZWJ (ex: desenvolvedor 👨‍💻) e seletores de variação (⚡️) não são corrompidos."""
        dev_text = "The developer 👨\u200d💻 created an AI model."
        normalized = normalize_text_spacing(dev_text)
        self.assertIn("\u200d", normalized, "O Zero-Width Joiner (ZWJ) de emojis compostos não deve ser expurgado!")
        self.assertIn("👨\u200d💻", normalized)

        translated = OfflineContextTranslator.translate(dev_text)
        self.assertIn("👨\u200d💻", translated, "Emoji composto deve ser preservado como glifo atômico sem espaços injetados no ZWJ!")

        # Valida seletor de variação (\ufe0f) em símbolos como raio (⚡️)
        symbol_text = "Warning: ⚡\ufe0f high voltage!"
        norm_sym = normalize_text_spacing(symbol_text)
        trans_sym = OfflineContextTranslator.translate(norm_sym)
        self.assertNotIn("⚡ ️", trans_sym, "Espaço não deve ser injetado entre o emoji e seu variation selector!")
        self.assertIn("⚡\ufe0f", trans_sym)

        # Valida emoji complexo com múltiplos ZWJs encadeados (família de 4 pessoas)
        family_text = "Family 👨\u200d👩\u200d👧\u200d👦 together."
        norm_fam = normalize_text_spacing(family_text)
        self.assertEqual(norm_fam.count("\u200d"), 3, "Todos os 3 ZWJs da sequência familiar devem ser preservados!")
        trans_fam = OfflineContextTranslator.translate(norm_fam)
        self.assertIn("👨\u200d👩\u200d👧\u200d👦", trans_fam)

    def test_18_extreme_history_cache_stress_and_untruncated_integrity(self):
        """Valida estresse com 50 entradas longas no cofre ACID e integridade 100% sem truncamento a 60 chars."""
        from ui_window import LoTraMainWindow

        long_entries = [
            (
                f"Long Article Section {i}: Deep neural networks utilize transformer architectures to process natural language tokens with self-attention mechanisms across multiple heads.",
                f"Seção de Artigo Longo {i}: Redes neurais profundas utilizam arquiteturas de transformadores para processar tokens de linguagem natural com mecanismos de autoatenção em múltiplas cabeças."
            )
            for i in range(50)
        ]

        for i, (src, trans) in enumerate(long_entries):
            self.vault.store_cache("extreme_stress_doc", i + 1, src, "", trans, "qwen2.5:1.5b", 12.5 + i)

        main_win = LoTraMainWindow(app=self.app)
        try:
            main_win._switch_tab("history")
            children = main_win.tree_history.get_children()
            self.assertGreaterEqual(len(children), 40, "Deve carregar histórico volumoso do cache.")

            # Valida que todos os itens carregados têm dados completos armazenados
            self.assertGreaterEqual(len(main_win._history_items_data), len(children))

            # Seleciona o primeiro item (mais recente inserido, index 49)
            main_win.tree_history.selection_set(children[0])
            main_win._load_selected_history_item()
            self.assertEqual(main_win.current_tab, "translate")

            loaded_src = main_win.txt_input.get("1.0", "end").strip()
            loaded_trans = main_win.txt_output.get("1.0", "end").strip()

            expected_src, expected_trans = long_entries[-1]
            self.assertEqual(loaded_src, expected_src, "Texto original não deve sofrer truncamento a 60 caracteres!")
            self.assertEqual(loaded_trans, expected_trans, "Texto traduzido não deve sofrer truncamento a 60 caracteres!")
            self.assertGreater(len(loaded_src), 100)
            self.assertGreater(len(loaded_trans), 120)

            # Valida cópia completa do histórico
            main_win._copy_selected_history_item()
            copied = get_windows_clipboard_text()
            self.assertEqual(copied, expected_trans)
        finally:
            try:
                main_win.root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()


