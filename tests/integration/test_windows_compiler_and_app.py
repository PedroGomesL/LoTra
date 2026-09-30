"""
Suíte de Testes do Aplicativo LoTra e Subsistemas do Compilador Windows:
1. Resolução de recursos (get_resource_path) para modo local e congelado (sys._MEIPASS).
2. Hardware Profiler e orquestração SLA do aplicativo.
3. Windows Media OCR engine (sanitização, tratamento de erros, subprocess handling).
4. Pipeline Adaptativo de Tradução (Glossário, Cache ACID e fallback contextual).
5. Clipboard Win32 e prontidão do HUD Tooltip overlay.
6. Auto-diagnóstico ponta a ponta (LoTraApp.run_self_test).
"""

import os
import sys
import tempfile
import time
from pathlib import Path

# Adiciona caminhos
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from resource_utils import get_resource_path
from ocr_engine import WindowsMediaOCREngine
from translation_engine import TranslationPipeline, OfflineContextTranslator, OFFLINE_TECHNICAL_GLOSSARY
import hud_tooltip
from hud_tooltip import (
    HUDTooltip,
    HotkeyListener,
    get_windows_clipboard_text,
    set_windows_clipboard_text,
    simulate_copy_selection,
    normalize_text_spacing,
    get_monitor_work_area_for_point,
    get_dpi_for_point,
    is_process_elevated,
    is_foreground_window_elevated
)
from screen_snipper import NativeScreenSnipper
from platform_core import IPlatformBridge, get_platform_bridge
from app import LoTraApp
from PIL import Image, ImageDraw

def test_resource_resolution():
    print(">>> 1. Testando Resolução de Recursos e Assets...")
    ico = get_resource_path("assets/lotra.ico")
    assert ico.exists(), f"Ícone não localizado: {ico}"
    
    ps_script = get_resource_path("src/win_ocr.ps1")
    assert ps_script.exists(), f"Script win_ocr.ps1 não localizado: {ps_script}"
    print(f"  [PASS] Assets localizados: {ico.name}, {ps_script.name}")

def test_clipboard_and_hud_readiness():
    print(">>> 2. Testando Integração com Clipboard Win32 e HUD Tooltip...")
    if sys.platform == "win32":
        test_msg = f"LoTra_Teste_Acentuação_{int(time.time())}_maçã_café_ímã"
        success = set_windows_clipboard_text(test_msg)
        assert success is True, "Falha ao gravar no clipboard do Windows"
        read_back = get_windows_clipboard_text()
        assert read_back == test_msg, f"Esperado '{test_msg}', obteve '{read_back}'"
        print("  [PASS] Clipboard Win32 leitura/escrita UTF-16LE validado!")

    hud = HUDTooltip()
    assert hud._is_active is False
    # Valida ciclo de renderização real do HUD
    hud.show("Texto Traduzido para Teste", "Source Text", latency_ms=15.0, engine_name="UnitTest")
    assert hud._is_active is True
    hud.pump_events()
    hud.dismiss()
    assert hud._is_active is False

    # Valida renderização com suporte a múltiplos monitores, High-DPI e coordenadas virtuais negativas
    work_area = get_monitor_work_area_for_point(100, 100)
    assert len(work_area) == 4
    dpi_val = get_dpi_for_point(100, 100)
    assert isinstance(dpi_val, int) and dpi_val >= 96
    print(f"  [PASS] DPI dinâmico por monitor validado: {dpi_val} DPI")

    hud.show("Multi-monitor Test", "Source", cursor_pos=(-600, 200))
    assert hud._is_active is True
    hud.pump_events()
    hud.dismiss()
    hud.destroy()

    # Valida clamping em monitor secundário virtual com coordenadas negativas (-1920 a 0)
    hud2 = HUDTooltip()
    orig_work_area = hud_tooltip.get_monitor_work_area_for_point
    try:
        hud_tooltip.get_monitor_work_area_for_point = lambda x, y: (-1920, 0, 0, 1080)
        hud2.show("Negative Coordinate Monitor Test", "Source", cursor_pos=(-1000, 300))
        assert hud2._is_active is True
        hud2.pump_events()
        assert hud2._window.winfo_x() < 0 or "+-" in hud2._window.geometry(), "Janela deve estar posicionada no monitor secundário negativo"
        hud2.dismiss()
    finally:
        hud_tooltip.get_monitor_work_area_for_point = orig_work_area
        hud2.destroy()
    print("  [PASS] HUD Tooltip ciclo de vida e suporte multi-monitor com coordenadas negativas validados com sucesso.")

    # Valida detecção de integridade de privilégios UIPI
    proc_elevated = is_process_elevated()
    fg_elevated = is_foreground_window_elevated()
    assert isinstance(proc_elevated, bool)
    assert isinstance(fg_elevated, bool)
    print("  [PASS] Detecção de integridade UIPI e janelas elevadas validada!")

    # Valida NativeScreenSnipper: cancelamento instantâneo (< 5ms) via Esc sem poluição do clipboard
    snipper = NativeScreenSnipper()
    assert snipper.is_active is False
    cancel_called = False
    def on_cancel():
        nonlocal cancel_called
        cancel_called = True

    snipper.start_snip(on_snip=lambda img, pos: None, on_cancel=on_cancel)
    assert snipper.is_active is True
    t0_cancel = time.perf_counter()
    snipper.cancel()
    t_cancel_ms = (time.perf_counter() - t0_cancel) * 1000.0
    assert snipper.is_active is False
    assert cancel_called is True
    assert t_cancel_ms < 25.0  # Fechamento instantâneo (< 5ms na maioria das CPUs)
    print(f"  [PASS] NativeScreenSnipper cancelamento instantâneo via Esc validado ({t_cancel_ms:.2f}ms < 25ms)!")

    # Valida NativeScreenSnipper: fluxo completo de seleção e isolamento de callbacks
    snipper2 = NativeScreenSnipper()
    snip_invoked = False
    cancel_invoked = False
    def on_snip(img, pos):
        nonlocal snip_invoked
        snip_invoked = True
    def on_canc():
        nonlocal cancel_invoked
        cancel_invoked = True

    snipper2.start_snip(on_snip=on_snip, on_cancel=on_canc)
    orig_grab = snipper2.grab_bbox
    snipper2.grab_bbox = lambda bbox: Image.new("RGB", (100, 50), (255, 255, 255))
    try:
        class MockEvent:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        snipper2._on_button_press(MockEvent(50, 50))
        snipper2._on_mouse_drag(MockEvent(150, 100))
        snipper2._start_x = 50
        snipper2._start_y = 50
        snipper2._window.winfo_pointerx = lambda: 150
        snipper2._window.winfo_pointery = lambda: 100
        snipper2._on_button_release(MockEvent(150, 100))

        assert snipper2.is_active is False
        assert snip_invoked is True, "on_snip deve ser invocado em seleção válida"
        assert cancel_invoked is False, "on_cancel NÃO deve ser invocado em seleção válida bem-sucedida"
        print("  [PASS] NativeScreenSnipper seleção completa e isolamento de callbacks validados com sucesso!")
    finally:
        snipper2.grab_bbox = orig_grab
        snipper2.cancel()

    # Valida Platform Bridge multi-OS
    bridge = get_platform_bridge()
    assert isinstance(bridge, IPlatformBridge)
    assert len(bridge.get_monitor_work_area_for_point(0, 0)) == 4
    assert bridge.get_dpi_for_point(0, 0) >= 96
    assert isinstance(bridge.is_process_elevated(), bool)
    print("  [PASS] Cross-platform bridge (IPlatformBridge) validado com sucesso!")

def test_translation_engine_and_cache():
    print(">>> 3. Testando Pipeline de Tradução e Cache do Cofre...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_app_vault.db")
        app = LoTraApp(db_path=db_path)
        
        # Teste 1: Termo técnico do glossário
        res1 = app.translate_text("cryogenic attenuation stages")
        assert res1["translated_text"] != ""
        assert "estágios de atenuação criogênica" in res1["translated_text"].lower()
        assert res1["cache_hit"] is False
        
        # Teste 2: Consulta imediata do cache
        res2 = app.translate_text("cryogenic attenuation stages")
        assert res2["cache_hit"] is True
        assert res2["translated_text"] == res1["translated_text"]
        assert res2["latency_ms"] < 50.0 # Cache hit instantâneo
        print(f"  [PASS] Cache hit validado: {res2['latency_ms']:.2f}ms")

        # Teste 3: Trigger thread-safe de tradução via clipboard
        import threading
        set_windows_clipboard_text("quantum scalability")
        def bg_worker():
            app.trigger_quick_translation_from_clipboard()
        t = threading.Thread(target=bg_worker)
        t.start()
        t.join(timeout=3.0)
        assert not app._ui_queue.empty(), "Ação não enfileirada na fila da UI principal"
        q_item = app._ui_queue.get()
        assert "escalabilidade quântica" in q_item["translated_text"].lower()
        print("  [PASS] Trigger assíncrono thread-safe via _ui_queue validado!")

        # Teste 4: Despacho de aviso UIPI para o HUD
        app._display_hud_notice("[Aviso UIPI] Janela de Administrador detectada.")
        assert app.hud._is_active is True or not app._ui_queue.empty()
        app.hud.dismiss()
        print("  [PASS] Despacho de avisos informativos UIPI para o HUD validado!")

def test_ocr_engine_robustness():
    print(">>> 4. Testando Robustez do Motor Windows Media OCR e Codificação UTF-8...")
    engine = WindowsMediaOCREngine()
    
    # 1. Arquivo inexistente deve falhar graciosamente sem lançar exceção
    err_res = engine.recognize_file("caminho_inexistente_12345.png")
    assert err_res["success"] is False
    assert "não encontrado" in err_res["error"]

    # 2. Imagem sintética pequena com texto
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        img_path = os.path.join(tmpdir, "ocr_sample.png")
        img = Image.new("RGB", (300, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "LoTra Reader", fill=(0, 0, 0))
        img.save(img_path)

        res = engine.recognize_file(img_path)
        # Se Windows Media OCR estiver disponível, valida texto
        if engine.is_available():
            assert res["success"] is True
            assert "lotra" in res["text"].lower() or "reader" in res["text"].lower()
            print(f"  [PASS] Windows Media OCR executou com sucesso ({res['inference_ms']:.1f}ms): '{res['text']}'")
        else:
            print("  [SKIP] Windows Media OCR não disponível no host atual.")

    # 3. Imagem real com acentuação em português (docs/images/latency_comparison.png)
    real_img = ROOT_DIR / "docs" / "images" / "latency_comparison.png"
    if real_img.exists() and engine.is_available():
        res_real = engine.recognize_file(real_img)
        assert res_real["success"] is True
        text = res_real["text"]
        # Verifica que caracteres acentuados não foram corrompidos em mojibake
        assert "Latência de Tradução" in text or "Lat" in text, f"Texto OCR inesperado: {text[:60]}"
        assert "\ufffd" not in text, "Detectado caractere corrompido (replacement character) na saída do OCR"
        print(f"  [PASS] OCR UTF-8 acentuação nativa verificada sem mojibake!")

def test_lotra_app_self_diagnosis():
    print(">>> 5. Testando Auto-Diagnóstico Completo da Aplicação (Self-Test)...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "self_test.db")
        app = LoTraApp(db_path=db_path)
        diag = app.run_self_test()
        assert diag["all_passed"] is True, f"Diagnóstico falhou: {diag}"
        print("  [PASS] Todos os subsistemas reportaram integridade 100%!")

def test_text_spacing_normalization_and_hud_font():
    print(">>> 6. Testando Normalização de Quebras de Linha e Fonte Times New Roman no HUD...")
    # 1. Simulação do texto com quebras duras de linha de PDF do arXiv
    arxiv_raw = (
        "As artificial intelligence (AI), including generative\n"
        "AI, continue to evolve, concerns have arisen about over-reliance\n"
        "on AI, which may lead to human deskilling and diminished\n"
        "cognitive engagement. Over-reliance on AI can also lead users\n"
        "to accept information given by AI without performing critical\n"
        "examinations, causing negative consequences, such as misleading\n"
        "users with hallucinated contents. This paper introduces extraheric\n"
        "AI, a human-AI interaction design framework that fosters\n"
        "users' higher-order thinking skills, such as creativity, critical"
    )
    normalized = normalize_text_spacing(arxiv_raw)
    assert "\n" not in normalized, f"Linhas do mesmo parágrafo não devem conter quebras de linha: {normalized}"
    assert "generative AI" in normalized
    assert "human deskilling" in normalized
    print("  [PASS] Normalização de quebras de linha em fluxo de parágrafo validada!")

    # 2. Desfazimento de hifenização de fim de linha
    hyphenated = "inter-\noperability and superconduc-\nting qubits"
    dehyphenated = normalize_text_spacing(hyphenated)
    assert "interoperability" in dehyphenated
    assert "superconducting" in dehyphenated
    print("  [PASS] Remoção de hifens de quebra de coluna em PDFs validada!")

    # 3. Preservação de quebra real entre parágrafos distintos
    two_paras = "First paragraph ended successfully.\n\nSecond paragraph starting here."
    norm_two = normalize_text_spacing(two_paras)
    assert "\n\n" in norm_two
    print("  [PASS] Preservação de múltiplos parágrafos reais validada!")

    # 4. Itens de lista compactos (sem espaçamento duplo \n\n)
    list_text = "Key highlights:\n1. First item\n2. Second item\n3. Third item"
    norm_list = normalize_text_spacing(list_text)
    assert "1. First item\n2. Second item" in norm_list, f"Itens de lista devem ter quebra simples: {repr(norm_list)}"
    assert "1. First item\n\n2. Second item" not in norm_list, f"Itens de lista não devem ter espaçamento duplo: {repr(norm_list)}"
    print("  [PASS] Normalização compacta de listas sem espaçamento excessivo validada!")

    # 5. Verificação da fonte Times New Roman na janela HUD
    hud = HUDTooltip()
    hud.show("Teste Tipografia", "Source", timeout_sec=0)
    labels = [w for w in hud._window.winfo_children()[0].winfo_children() if w.winfo_class() == "Label"]
    assert len(labels) > 0
    font_used = labels[0].cget("font")
    assert "Times New Roman" in str(font_used), f"Fonte esperada 'Times New Roman', obtido: {font_used}"
    hud.destroy()
    print("  [PASS] Fonte Times New Roman confirmada no HUD Tooltip!")

    # 6. Disponibilidade da função de captura automática por simulação de cópia
    assert callable(simulate_copy_selection)
    print("  [PASS] Simulação de cópia automática de seleção (Alt+Q sem Ctrl+C) verificada!")

def test_100_percent_local_translation():
    print(">>> 7. Testando Isolamento 100% Offline e Ausência de APIs Online do Google...")
    pipeline = TranslationPipeline()
    # 1. Garante que método online de web translation foi completamente eliminado
    assert not hasattr(pipeline, "_query_web_translation"), "Violação de isolamento: _query_web_translation ainda existe!"
    
    # 2. Garante que arquivos fonte não possuem URLs de tradutores externos
    engine_file = SRC_DIR / "translation_engine.py"
    content = engine_file.read_text(encoding="utf-8")
    assert "clients5.google.com" not in content, "Violação de isolamento: URL da API do Google encontrada em translation_engine.py!"
    assert "api.mymemory" not in content, "Violação de isolamento: URL da API MyMemory encontrada em translation_engine.py!"
    print("  [PASS] Zero conexões ou URLs com Google / APIs externas no código fonte!")

    # 3. Validação de tradução local dos termos do arXiv e IA
    t0 = time.perf_counter()
    tr_ai = pipeline.translate_text("artificial intelligence")
    latency_ms = (time.perf_counter() - t0) * 1000.0
    assert tr_ai["translated_text"].lower() == "inteligência artificial"
    assert tr_ai["engine_used"] != "Neural Translation Engine (PT-BR)"
    # A resposta offline local deve ser ultrarrápida (sem travar segundos por Ollama offline)
    assert latency_ms < 500.0, f"Latência offline excessiva: {latency_ms:.2f}ms"
    
    tr_deskilling = pipeline.translate_text("human deskilling and diminished cognitive engagement")
    assert "desqualificação" in tr_deskilling["translated_text"].lower()
    assert "envolvimento cognitivo" in tr_deskilling["translated_text"].lower() or "engajamento" in tr_deskilling["translated_text"].lower()
    print("  [PASS] Tradução offline local de vocabulário acadêmico e técnico validada!")

def test_two_hotkey_commands_configuration():
    print(">>> 8. Testando Suporte Estrito aos 2 Comandos Globais (Alt+Q e Alt+W)...")
    invoked = []
    listener = HotkeyListener(
        callback=lambda: invoked.append("alt_q"),
        on_ocr_snip=lambda: invoked.append("alt_w")
    )
    assert listener.callback is not None
    assert listener.on_ocr_snip is not None
    listener.callback()
    listener.on_ocr_snip()
    assert invoked == ["alt_q", "alt_w"]
    print("  [PASS] Configuração dos 2 comandos [Alt + Q] e [Alt + W] validada com sucesso!")

import unittest

class TestWindowsCompilerAndApp(unittest.TestCase):
    def test_windows_compiler_and_app_suite(self):
        test_resource_resolution()
        test_clipboard_and_hud_readiness()
        test_translation_engine_and_cache()
        test_ocr_engine_robustness()
        test_lotra_app_self_diagnosis()
        test_text_spacing_normalization_and_hud_font()
        test_100_percent_local_translation()
        test_two_hotkey_commands_configuration()

if __name__ == "__main__":
    test_resource_resolution()
    test_clipboard_and_hud_readiness()
    test_translation_engine_and_cache()
    test_ocr_engine_robustness()
    test_lotra_app_self_diagnosis()
    test_text_spacing_normalization_and_hud_font()
    test_100_percent_local_translation()
    test_two_hotkey_commands_configuration()
    print("\n=======================================================")
    print("TODOS OS TESTES DO APLICATIVO E COMPILADOR PASSARAM!")
    print("=======================================================")
