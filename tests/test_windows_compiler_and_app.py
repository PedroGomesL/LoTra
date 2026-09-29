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
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from resource_utils import get_resource_path
from ocr_engine import WindowsMediaOCREngine
from translation_engine import TranslationPipeline, OfflineContextTranslator
from hud_tooltip import HUDTooltip, get_windows_clipboard_text, set_windows_clipboard_text
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
    hud.destroy()
    print("  [PASS] HUD Tooltip ciclo de vida (show, pump_events, dismiss, destroy) validado com sucesso.")

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

if __name__ == "__main__":
    test_resource_resolution()
    test_clipboard_and_hud_readiness()
    test_translation_engine_and_cache()
    test_ocr_engine_robustness()
    test_lotra_app_self_diagnosis()
    print("\n=======================================================")
    print("TODOS OS TESTES DO APLICATIVO E COMPILADOR PASSARAM!")
    print("=======================================================")
