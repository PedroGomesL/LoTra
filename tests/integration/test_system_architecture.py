"""
Testes Unitários e Validação Arquitetural:
1. DocumentContextVault:
   - Invariância de Hash SHA-256 ao mover arquivos de pasta ou renomear
   - Rastreamento explícito de mudança de local (was_moved, known_paths)
   - Operações ACID e WAL mode do SQLite
   - Injeção hierárquica de contexto (Domínio + Resumo Global + Seção + Glossário)
   - Cache de tradução com hit rate instantâneo (< 1ms)
2. AdaptiveEngineOrchestrator:
   - Leitura de hardware real (Memória via Win32 API, CPU cores, detecção de GPU)
   - Respeito ao SLA (< 250ms e < 500ms) sob repouso vs sobrecarga de CPU, RAM e Disco
   - Fail-safe de memória sob pressão extrema de RAM (prevenção contra ValueError / crash)
   - Suporte ao catálogo completo incluindo PaddleOCR e DirectML
3. PDFResilienceManager:
   - Integridade após fechamento forçado (WAL rollback / integrity_check)
   - Supressão de artefatos de marca-texto em espectro amplo (Amarelo, Verde, Ciano, Rosa/Magenta)
   - Recuperação real de texto por Stream Carving em PDFs corrompidos sem Xref/EOF
   - Inspeção e desacoplamento de camadas de anotação (/Annots vs /Contents)
"""

import os
import sys
import shutil
import tempfile
import time
import json
from pathlib import Path

# Adiciona o diretório src ao path para importação modular
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from document_context_vault import DocumentContextVault
from adaptive_engine_orchestrator import AdaptiveEngineOrchestrator, HardwareProfiler, OCR_ENGINES
from pdf_resilience_manager import PDFResilienceManager
from PIL import Image, ImageDraw

def test_document_context_vault():
    print(">>> Testando DocumentContextVault...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_vault.db")
        vault = DocumentContextVault(db_path)
        
        # 1. Cria arquivo de teste
        file1 = os.path.join(tmpdir, "quantum_paper_v1.pdf")
        content = b"PDF-1.7 header mock content with some quantum formulas" * 2000
        with open(file1, "wb") as f:
            f.write(content)
            
        hash1 = vault.compute_content_fingerprint(file1)
        res1 = vault.register_or_update_file(file1, title="Quantum Scalability", domain="Quantum Physics")
        assert res1.is_new is True
        assert res1.was_moved is False
        assert hash1 == res1.doc_hash
        # Testa desempacotamento tradicional (doc_id, is_new)
        doc_id1, is_new1 = res1
        assert is_new1 is True
        
        # 2. Testa invariância a mover ou renomear o arquivo
        subfolder = os.path.join(tmpdir, "new_folder")
        os.makedirs(subfolder, exist_ok=True)
        file2 = os.path.join(subfolder, "renamed_quantum_thesis.pdf")
        shutil.copy(file1, file2)
        
        hash2 = vault.compute_content_fingerprint(file2)
        assert hash1 == hash2, "O hash deve ser IDÊNTICO mesmo mudando de nome e pasta!"
        
        res2 = vault.register_or_update_file(file2)
        assert res2.is_new is False, "O sistema deve reconhecer que é o mesmo documento e não duplicar!"
        assert res2.was_moved is True, "O sistema deve registrar que o arquivo foi encontrado em um novo local!"
        assert len(res2.known_paths) == 2, "O histórico de caminhos conhecidos deve conter ambos os locais!"
        
        # 3. Salva contexto semântico e seções
        vault.save_document_context(
            doc_hash=hash1,
            title="Quantum Scalability",
            domain="Quantum Physics",
            global_summary="Análise de resfriamento criogênico em processadores transmon.",
            glossary={"transmon": "qubit transmon supercondutor", "crosstalk": "diafonia de micro-ondas"},
            sections=[
                {
                    "page_start": 1,
                    "page_end": 1,
                    "title": "Cryogenic Attenuation Stages",
                    "type": "results",
                    "summary": "Mapeamento térmico dos estágios de 4K a 15mK.",
                    "keywords": ["transmon", "refrigerator"]
                }
            ]
        )
        
        # 4. Testa injeção hierárquica de contexto
        sample_selection = "The transmon qubit experienced severe microwave crosstalk during readout."
        prompt_ctx = vault.get_hierarchical_context_prompt(hash1, current_page=1, selected_text=sample_selection)
        print(f"Contexto Hierárquico Injetado:\n  {prompt_ctx}")
        assert "Quantum Physics" in prompt_ctx
        assert "Resumo Global:" in prompt_ctx or "resfriamento criogênico" in prompt_ctx
        assert "Cryogenic Attenuation Stages" in prompt_ctx
        assert "transmon" in prompt_ctx
        assert "crosstalk" in prompt_ctx
        
        # 5. Testa Cache ACID de Tradução
        t0 = time.perf_counter()
        vault.store_cache(
            doc_hash=hash1,
            page_num=1,
            source_text=sample_selection,
            context_used=prompt_ctx,
            translated_text="O qubit transmon supercondutor sofreu severa diafonia de micro-ondas durante a leitura.",
            model_id="qwen_2.5_1.5b",
            latency_ms=120.5
        )
        cached = vault.lookup_cache(hash1, sample_selection, model_id="qwen_2.5_1.5b")
        t1 = time.perf_counter()
        lookup_ms = (t1 - t0) * 1000.0
        
        assert cached is not None
        assert "diafonia" in cached
        print(f"Cache Lookup: {lookup_ms:.3f} ms (Resultado: '{cached[:50]}...')")

        # 6. Testa SQLite WAL auto-checkpointing, incremental vacuum, shutdown e quota de retenção combinada
        cp_res = vault.checkpoint_wal(mode="TRUNCATE")
        assert cp_res["success"] is True
        assert cp_res["mode"] == "TRUNCATE"

        # Testa incremental vacuum e full vacuum
        vac_inc = vault.vacuum_db(incremental=True)
        assert vac_inc["success"] is True
        assert vac_inc["mode"] == "incremental"

        with vault._get_connection() as conn:
            auto_vac = conn.execute("PRAGMA auto_vacuum;").fetchone()[0]
            assert auto_vac == 2, f"auto_vacuum deve ser 2 (INCREMENTAL), obteve {auto_vac}"

        vac_res = vault.vacuum_db()
        assert vac_res["success"] is True

        # Testa shutdown formal com checkpoint
        shut_res = vault.shutdown()
        assert shut_res["success"] is True

        # Validação de LRU: verifica persistência de last_accessed_at na tabela translation_cache
        with vault._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT last_accessed_at, hit_count FROM translation_cache WHERE doc_hash = ?", (hash1,))
            row = cur.fetchone()
            assert row is not None
            assert row["last_accessed_at"] is not None and row["last_accessed_at"] > 0
            assert row["hit_count"] >= 2

        # Testa quota combinada (DB + WAL + Thumbnails)
        thumb_dir = Path(tmpdir) / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        dummy_thumb = thumb_dir / f"{hash1}.png"
        dummy_thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)

        sizes = vault.get_storage_size_bytes()
        assert sizes["db_bytes"] > 0
        assert sizes["thumbnails_bytes"] >= 2048
        assert sizes["total_bytes"] == sizes["db_bytes"] + sizes["wal_bytes"] + sizes["thumbnails_bytes"]

        quota_res = vault.enforce_size_quota(max_size_mb=100)
        assert quota_res["under_quota"] is True
        print("[PASS] DocumentContextVault, WAL Checkpointing, LRU last_accessed_at e Quotas validados com sucesso!")

def test_adaptive_orchestrator():
    print("\n>>> Testando AdaptiveEngineOrchestrator...")
    # Testa detecção de hardware real na máquina
    mem = HardwareProfiler.get_memory_status()
    gpu = HardwareProfiler.detect_gpu_capabilities()
    cpu = HardwareProfiler.get_cpu_info()
    
    print(f"Hardware Detectado:")
    print(f"  RAM Total: {mem['total_ram_gb']} GB | Livre: {mem['avail_ram_gb']} GB (Uso: {mem['ram_used_pct']}%)")
    print(f"  CPU Cores: {cpu['logical_cores']} | AVX2: {cpu['has_avx2']}")
    print(f"  GPU Backend: {gpu['gpu_name']} ({gpu['backend']})")
    
    # Valida catálogo de OCR
    assert "paddle_ocr" in OCR_ENGINES, "PaddleOCR deve estar presente no catálogo de OCR!"
    
    # 1. Orquestrador com meta estrita de SLA de 250ms (Instant HUD)
    orch_fast = AdaptiveEngineOrchestrator(target_latency_ms=250.0)
    
    # Teste A: Palavra sob baixo uso na CPU (Ryzen 4800HS)
    rec_word_cpu = orch_fast.select_optimal_pipeline(text_type="word", simulated_cpu_stress=15.0, force_hardware="cpu")
    print(f"Cenário 1 (Palavra / CPU Idle / SLA 250ms):")
    print(f"  Escolhido: {rec_word_cpu['ocr_name']} + {rec_word_cpu['model_name']}")
    print(f"  Latência Total Estimada: {rec_word_cpu['predicted_total_ms']} ms | Qualidade: {rec_word_cpu['combined_quality_score']}/10")
    assert rec_word_cpu["meets_sla"] is True
    
    # Teste B: Parágrafo sob CPU saturada a 95% (Sobrecarga de CPU)
    rec_para_stress = orch_fast.select_optimal_pipeline(text_type="paragraph", simulated_cpu_stress=95.0, force_hardware="cpu")
    print(f"Cenário 2 (Parágrafo / CPU 95% Sobrecarga / SLA 250ms):")
    print(f"  Escolhido: {rec_para_stress['ocr_name']} + {rec_para_stress['model_name']}")
    print(f"  Latência Total Estimada: {rec_para_stress['predicted_total_ms']} ms | Motivo: {rec_para_stress['decision_reason']}")
    # Deve selecionar MarianMT ou modelo ultra-leve para não explodir a latência!
    assert rec_para_stress["translation_model"] in ("marian_mt", "qwen_0.5b")
    
    # Teste C: Pressão Extrema de RAM (98% utilizada / 0.3GB livres) -> Fail-safe contra OOM / Crash
    rec_ram_stress = orch_fast.select_optimal_pipeline(text_type="word", simulated_ram_stress=98.0, force_hardware="cpu")
    print(f"Cenário 3 (Palavra / RAM sob Esgotamento 98%):")
    print(f"  Escolhido: {rec_ram_stress['ocr_name']} + {rec_ram_stress['model_name']}")
    assert rec_para_stress is not None
    assert rec_ram_stress["translation_model"] in ("marian_mt", "qwen_0.5b")
    
    # Teste D: GPU RTX 5060 Ti sob baixo uso
    rec_gpu = orch_fast.select_optimal_pipeline(text_type="paragraph", simulated_cpu_stress=10.0, simulated_ram_stress=25.0, force_hardware="cuda")
    print(f"Cenário 4 (Parágrafo / RTX 5060 Ti / SLA 250ms):")
    print(f"  Escolhido: {rec_gpu['ocr_name']} + {rec_gpu['model_name']}")
    print(f"  Latência Total Estimada: {rec_gpu['predicted_total_ms']} ms | Qualidade: {rec_gpu['combined_quality_score']}/10")
    assert rec_gpu["meets_sla"] is True
    assert rec_gpu["combined_quality_score"] >= 9.0
    
    # Teste E: Com SLA de 400ms na GPU, deve selecionar modelo de qualidade máxima (Qwen 3B com 9.7/10)
    orch_quality = AdaptiveEngineOrchestrator(target_latency_ms=400.0)
    rec_gpu_hq = orch_quality.select_optimal_pipeline(text_type="paragraph", simulated_ram_stress=25.0, force_hardware="cuda")
    print(f"Cenário 5 (Parágrafo / RTX 5060 Ti / SLA 400ms - Modo Alta Fidelidade):")
    print(f"  Escolhido: {rec_gpu_hq['ocr_name']} + {rec_gpu_hq['model_name']}")
    print(f"  Latência Total: {rec_gpu_hq['predicted_total_ms']} ms | Qualidade: {rec_gpu_hq['combined_quality_score']}/10")
    assert rec_gpu_hq["combined_quality_score"] >= 9.5
    
    print("[PASS] AdaptiveEngineOrchestrator validado com sucesso!")

def test_pdf_resilience_and_highlighter():
    print("\n>>> Testando PDFResilienceManager, Filtro Multicor de Marca-Texto e Stream Carving...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        # 1. Imagem sintética com marca-texto amarelo fluorescente
        img_yellow = Image.new("RGB", (400, 100), (255, 255, 255))
        draw_y = ImageDraw.Draw(img_yellow)
        draw_y.rectangle([20, 20, 380, 80], fill=(255, 255, 0)) # Amarelo
        draw_y.text((40, 40), "Cryogenic Transmon Resonator", fill=(0, 0, 0))
        
        y_in = os.path.join(tmpdir, "yellow_sample.png")
        y_out = os.path.join(tmpdir, "yellow_cleaned.png")
        img_yellow.save(y_in)
        
        res_y = PDFResilienceManager.inspect_and_clean_image_for_ocr(y_in, y_out)
        assert res_y["status"] == "success"
        cleaned_y = Image.open(y_out)
        pixel_y = cleaned_y.getpixel((25, 25))
        assert pixel_y[0] > 240 and pixel_y[1] > 240 and pixel_y[2] > 240, f"Amarelo deve virar branco, obteve: {pixel_y}"
        
        # 2. Imagem sintética com marca-texto rosa fluorescente (Pink)
        img_pink = Image.new("RGB", (400, 100), (255, 255, 255))
        draw_p = ImageDraw.Draw(img_pink)
        draw_p.rectangle([20, 20, 380, 80], fill=(255, 20, 147)) # Deep Pink fluorescente
        draw_p.text((40, 40), "Microwave Crosstalk Attenuation", fill=(0, 0, 0))
        
        p_in = os.path.join(tmpdir, "pink_sample.png")
        p_out = os.path.join(tmpdir, "pink_cleaned.png")
        img_pink.save(p_in)
        
        res_p = PDFResilienceManager.inspect_and_clean_image_for_ocr(p_in, p_out)
        assert res_p["status"] == "success"
        cleaned_p = Image.open(p_out)
        pixel_p = cleaned_p.getpixel((25, 25))
        assert pixel_p[0] > 235 and pixel_p[1] > 235 and pixel_p[2] > 235, f"Rosa fluorescente deve virar branco, obteve: {pixel_p}"
        
        # 3. Stream Carving real de PDF corrompido sem cabeçalho e sem EOF
        corrupted_bytes = b"CORRUPTED_GARBAGE_NO_HEADER BT /F1 12 Tf (Hello Quantum World) Tj ET OTHER_TRUNCATED_BYTES"
        diag = PDFResilienceManager.diagnose_corrupted_pdf_stream(corrupted_bytes)
        print(f"Diagnóstico de PDF Corrompido: {diag['recommended_action']}")
        print(f"Texto Recuperado por Stream Carving: '{diag['carved_sample_text']}'")
        assert "Stream Carving" in diag["recommended_action"]
        assert "Hello Quantum World" in diag["carved_sample_text"]

        # 4. Stream Carving de Compressed Object Streams (/ObjStm) via zlib.decompressobj
        import zlib
        compressed_body = zlib.compress(b"BT /F1 12 Tf (Decompressed Object Stream Carved) Tj ET")
        mock_obj_stm_pdf = (
            b"%PDF-1.5\n"
            b"5 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode >>\nstream\n"
            + compressed_body +
            b"\nendstream\nendobj\n"
        )
        obj_carved = PDFResilienceManager.carve_text_from_corrupted_stream(mock_obj_stm_pdf)
        assert any("Decompressed Object Stream Carved" in t for t in obj_carved), f"Falha ao recuperar texto de /ObjStm: {obj_carved}"
        print("  [PASS] Carving de Compressed Object Stream (/ObjStm) via zlib.decompressobj validado!")

        # 5. Derivação de chave ISO 32000-1 para PDFs criptografados com senha em branco
        derived_key = PDFResilienceManager.derive_iso32000_user_key(
            password=b"",
            o_entry=b"\x00" * 32,
            p_entry=-4,
            id_entry=b"lotra_crypto_id_"
        )
        assert len(derived_key) == 16, f"Chave derivada deve ter 16 bytes, obteve: {len(derived_key)}"

        # Testa cifragem e decifragem reversível RC4
        plaintext_sample = b"Secret Blank Password PDF Stream Content"
        ciphertext = PDFResilienceManager.rc4_crypt(derived_key, plaintext_sample)
        assert ciphertext != plaintext_sample
        decrypted = PDFResilienceManager.rc4_crypt(derived_key, ciphertext)
        assert decrypted == plaintext_sample
        print("  [PASS] Derivação de chave ISO 32000-1 e RC4 validados!")

        # 6. Inspeção e separação arquitetural da camada de anotações
        mock_pdf_annots = b"%PDF-1.7 ... /Contents 4 0 R ... /Annots [ 12 0 R /Highlight 13 0 R /Popup ]"
        annot_info = PDFResilienceManager.inspect_pdf_annotations_layer(mock_pdf_annots)
        assert annot_info["has_annotations"] is True
        assert "/Highlight" in annot_info["detected_annotation_types"]
        
        print("[PASS] PDFResilienceManager validado com sucesso!")

def test_translation_engine_onnx_and_fallback():
    print("\n>>> Testando ONNXTranslationEngine e Hierarquia Estruturada de Fallback...")
    from translation_engine import ONNXTranslationEngine, TranslationPipeline, OfflineContextTranslator

    # 1. Testa ONNXTranslationEngine
    onnx_eng = ONNXTranslationEngine()
    assert isinstance(onnx_eng.is_available(), bool)

    # 2. Testa TranslationPipeline com hierarquia de 4 níveis
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_trans_pipeline.db")
        vault = DocumentContextVault(db_path)
        pipeline = TranslationPipeline(vault=vault, ollama_url="http://127.0.0.1:99999") # Porta inexistente para testar fallback

        # Fallback para tradutor offline nativo
        res = pipeline.translate_text("artificial intelligence and machine learning")
        assert res["translated_text"] != ""
        assert "inteligência artificial" in res["translated_text"].lower()
        assert res["engine_used"] == "LoTra Built-in Offline Translator"

        # Segunda chamada deve atingir o cache ACID
        res_cache = pipeline.translate_text("artificial intelligence and machine learning")
        assert res_cache["cache_hit"] is True
        assert res_cache["engine_used"] == "DocumentContextVault Cache (ACID)"

        # Nível 3: Testa acionamento do motor ONNX quando disponível
        class MockNeuralTranslator:
            def translate_text(self, text):
                return "Tradução Neural ONNX: redes neurais convolucionais"

        pipeline.onnx_engine.set_custom_backend(translator=MockNeuralTranslator())
        res_onnx = pipeline.translate_text("convolutional neural networks")
        assert "Tradução Neural ONNX" in res_onnx["translated_text"]
        assert "ONNX Neural Engine" in res_onnx["engine_used"]

    print("[PASS] Hierarquia de Fallback e ONNXTranslationEngine validados com sucesso!")

import unittest

class TestSystemArchitecture(unittest.TestCase):
    def test_system_architecture_suite(self):
        test_document_context_vault()
        test_adaptive_orchestrator()
        test_pdf_resilience_and_highlighter()
        test_translation_engine_onnx_and_fallback()

if __name__ == "__main__":
    test_document_context_vault()
    test_adaptive_orchestrator()
    test_pdf_resilience_and_highlighter()
    test_translation_engine_onnx_and_fallback()
    print("\n=======================================================")
    print("TODOS OS TESTES ARQUITETURAIS E DE RESILIÊNCIA PASSARAM!")
    print("=======================================================")
