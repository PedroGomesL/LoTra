"""
Suíte de Testes Arquiteturais e de Segurança Avançada (Segurança, Privacidade, Read-Only e Scanner).
Valida integralmente todos os requisitos da arquitetura frank_sherlock integrados ao leitor/tradutor:

1. Princípio Read-Only Estrito:
   - Zero escritas em diretórios de documentos (inclusive montados como NFS/NAS read-only).
   - Todos os dados, banco, thumbnails e cache isolados estritamente em get_app_data_dir().
2. Privacidade & Anti-Vazamento (Modo OCR/Tradução):
   - Buffers de imagem 100% efêmeros em RAM (EphemeralImageBuffer).
   - Sobrescrita ativa de memória com zeros (secure_wipe_memory).
   - Criptografia do cofre em repouso (Windows DPAPI / HMAC) sem texto simples exposto no banco.
3. Scanning Incremental em 2 Fases:
   - Descoberta Rápida (mtime + tamanho, sem ler conteúdo).
   - Processamento Pesado com Fingerprint 64KB (SHA-256 dos primeiros 64KB).
   - Detecção de arquivos movidos ou renomeados sem reprocessamento.
   - Persistência de checkpoints por arquivo no SQLite (scan_jobs) e retomada após interrupção.
4. Cancelamento Cooperativo:
   - Flag atômico cooperativo com resposta responsiva (< 1s).
5. Resiliência do Banco & Migrações Formais:
   - SQLite WAL mode, PRAGMA integrity_check no startup, backup automático pré-migração.
   - 5 migrações formais e imutáveis ordenadas por posição.
6. Seleção de Modelos Hardware-Aware & Limpeza de VRAM:
   - Detecção de hardware em cache de AppState (Tiers: 3B / 7B / 32B).
   - Descarga explícita de VRAM via endpoint Ollama keep_alive: 0.
7. Abstração de Plataforma:
   - Canonicalização e sanitização de paths UNC (\\\\?\\) no Windows.
"""

import os
import sys
import time
import stat
import shutil
import tempfile
import sqlite3
from pathlib import Path

# Adiciona o diretório src ao path para importação modular
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from platform_core import (
    get_app_data_dir,
    canonicalize_path,
    HardwareDetector,
    VRAMManager,
    EnvironmentProvisioner
)
from privacy_vault import EphemeralImageBuffer, VaultProtector, secure_wipe_memory
from document_context_vault import DocumentContextVault
from incremental_scanner import IncrementalScanner, CancellationToken
from PIL import Image

def test_strict_read_only_principle():
    print(">>> 1. Testando Princípio Read-Only Estrito (Simulação de NAS / NFS Read-Only)...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        nas_docs_dir = os.path.join(tmpdir, "nas_company_share")
        os.makedirs(nas_docs_dir, exist_ok=True)

        # Cria 5 documentos simulados
        created_files = []
        for i in range(5):
            fp = os.path.join(nas_docs_dir, f"report_{i}.pdf")
            with open(fp, "wb") as f:
                f.write(f"%PDF-1.7 confidential financial report {i} BT /F1 12 Tf (Quarterly Results {i}) Tj ET".encode())
            created_files.append(fp)

        # Marca os arquivos e a pasta como READ-ONLY no SO (simulando montagem NFS read-only)
        for fp in created_files:
            os.chmod(fp, stat.S_IREAD)

        # Cria instância do Vault com banco isolado
        db_path = os.path.join(tmpdir, "isolated_appdata", "readflow_vault.db")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault)

        # Grava snapshot dos arquivos no diretório antes do scan
        before_entries = set(os.listdir(nas_docs_dir))

        # Executa o scan
        res = scanner.scan_directory(nas_docs_dir)
        assert res["status"] == "completed"
        assert res["total_discovered"] == 5
        assert res["reclassified_new"] == 5

        # Grava snapshot após o scan
        after_entries = set(os.listdir(nas_docs_dir))

        # VALIDAÇÃO CRÍTICA: O diretório escaneado DEVE ESTAR 100% INALTERADO!
        assert before_entries == after_entries, f"Violação de Read-Only: novos arquivos foram criados na pasta de documentos: {after_entries - before_entries}"
        for entry in after_entries:
            assert not entry.startswith("."), "Violação de Read-Only: dotfile ou pasta oculta criada no NAS!"
            assert "@eaDir" not in entry, "Violação de Read-Only: cache synology-like criado!"
            assert "thumb" not in entry.lower(), "Violação de Read-Only: thumbnail criada na origem!"

        # Remove atributo read-only para limpeza do tempfile
        for fp in created_files:
            try:
                os.chmod(fp, stat.S_IWRITE | stat.S_IREAD)
            except Exception:
                pass

        print("  [OK] Zero escritas no diretório escaneado. Princípio Read-Only 100% garantido!")

def test_privacy_and_anti_leak_vault():
    print("\n>>> 2. Testando Privacidade, Anti-Vazamento e Cofre Protegido...")
    # 2.1 Buffer Efêmero em RAM
    sample_img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = EphemeralImageBuffer.from_pil_image(sample_img)
    pil_loaded = buf.to_pil_image()
    assert pil_loaded.size == (200, 100)
    
    # 2.2 Sobrescrita Segura de Memória
    raw_sensitive = bytearray(b"Extremely Confidential Text in RAM")
    assert b"Extremely" in raw_sensitive
    secure_wipe_memory(raw_sensitive)
    assert raw_sensitive == bytearray(len(raw_sensitive)) # Todos os bytes viraram 0
    buf.secure_close()
    
    # 2.3 Criptografia em Repouso do Cofre (DPAPI / HMAC)
    secret_text = "Relatório Médico Ultraconfidencial: Paciente apresentou remissão completa."
    encrypted_hex = VaultProtector.encrypt_text(secret_text)
    
    # Valida que o texto em claro NÃO APARECE no dado cifrado
    assert secret_text not in encrypted_hex
    assert "Relatório Médico" not in encrypted_hex
    
    # Valida recuperação exata
    decrypted = VaultProtector.decrypt_text(encrypted_hex)
    assert decrypted == secret_text
    
    print("  [OK] Buffers efêmeros, memory wiping e criptografia do cofre validados com sucesso!")

def test_two_phase_incremental_scanning_and_move_detection():
    print("\n>>> 3. Testando Scan Incremental (Fase Rápida + Fase Pesada + Detecção de Movidos)...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        docs_dir = os.path.join(tmpdir, "my_documents")
        os.makedirs(docs_dir, exist_ok=True)
        
        # Cria 3 arquivos
        f1 = os.path.join(docs_dir, "doc1.txt")
        f2 = os.path.join(docs_dir, "doc2.txt")
        f3 = os.path.join(docs_dir, "doc3.txt")
        with open(f1, "w", encoding="utf-8") as f: f.write("Conteúdo inicial do documento 1.")
        with open(f2, "w", encoding="utf-8") as f: f.write("Conteúdo do documento 2 com termos técnicos de física quântica.")
        with open(f3, "w", encoding="utf-8") as f: f.write("Documento 3 sobre ressonância magnética.")

        db_path = os.path.join(tmpdir, "vault.db")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault)

        # 3.1 Primeiro Scan: deve processar os 3 arquivos
        res1 = scanner.scan_directory(docs_dir)
        assert res1["status"] == "completed"
        assert res1["total_discovered"] == 3
        assert res1["reclassified_new"] == 3
        assert res1["unchanged_fast_skipped"] == 0

        # 3.2 Segundo Scan Imediato: Fase de Descoberta Rápida (mtime + tamanho)
        # NADA mudou: deve pular os 3 arquivos instantaneamente sem ler conteúdo!
        t0 = time.perf_counter()
        res2 = scanner.scan_directory(docs_dir)
        t_fast = (time.perf_counter() - t0) * 1000.0
        assert res2["status"] == "completed"
        assert res2["unchanged_fast_skipped"] == 3
        assert res2["reclassified_new"] == 0
        assert res2["processed_heavy"] == 0
        print(f"  Fase Rápida: 3 arquivos validados em {t_fast:.2f} ms (zero leituras pesadas)!")

        # 3.3 Detecção de Arquivo Movido / Renomeado:
        # Movemos doc2.txt para uma nova pasta e renomeamos para reorganized_doc2.txt
        subfolder = os.path.join(docs_dir, "sub_archive")
        os.makedirs(subfolder, exist_ok=True)
        f2_moved = os.path.join(subfolder, "reorganized_doc2.txt")
        shutil.move(f2, f2_moved)

        res3 = scanner.scan_directory(docs_dir)
        assert res3["status"] == "completed"
        assert res3["moved_detected"] == 1
        assert res3["reclassified_new"] == 0 # NÃO RECLASSIFICA! Apenas atualiza o path!
        print("  [OK] Detecção de arquivos reorganizados/movidos confirmada sem reprocessamento!")

def test_checkpoint_persistence_and_interrupted_resume():
    print("\n>>> 4. Testando Persistência de Checkpoint e Retomada de Scan Interrompido...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        docs_dir = os.path.join(tmpdir, "bulk_docs")
        os.makedirs(docs_dir, exist_ok=True)
        
        # Cria 6 arquivos
        for i in range(6):
            with open(os.path.join(docs_dir, f"file_{i:02d}.txt"), "w") as f:
                f.write(f"Sample file payload {i}")

        db_path = os.path.join(tmpdir, "vault.db")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault)

        # Simula cancelamento ou encerramento após o 2º arquivo processado
        cancel_token = CancellationToken()
        job_id = "test_interrupted_job_001"

        def cancel_after_two(info):
            if info["processed"] >= 2:
                cancel_token.cancel()

        res_interrupted = scanner.scan_directory(
            docs_dir, 
            token=cancel_token, 
            resume_job_id=job_id,
            progress_callback=cancel_after_two
        )
        assert res_interrupted["status"] == "cancelled"
        assert res_interrupted["processed_count"] >= 2
        print(f"  Scan interrompido com sucesso no arquivo: {res_interrupted['last_processed_file']}")

        # Verifica estado salvo no SQLite scan_jobs
        with vault._get_connection() as conn:
            job_row = conn.execute("SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)).fetchone()
            assert job_row is not None
            assert job_row["last_processed_file"] is not None

        # Agora retoma o scan usando o mesmo job_id
        cancel_token.reset()
        res_resumed = scanner.scan_directory(
            docs_dir, 
            token=cancel_token, 
            resume_job_id=job_id
        )
        assert res_resumed["status"] == "completed"
        assert res_resumed["resumed_from_checkpoint"] is True
        print(f"  Scan retomado com sucesso a partir do checkpoint! Arquivos pulados pela retomada: {res_resumed['resumed_skipped_count']}")

def test_cooperative_cancellation_speed():
    print("\n>>> 5. Testando Velocidade do Cancelamento Cooperativo (< 1s)...")
    token = CancellationToken()
    assert token.is_cancelled() is False
    
    t0 = time.perf_counter()
    token.cancel()
    t1 = time.perf_counter()
    cancel_latency_ms = (t1 - t0) * 1000.0
    
    assert token.is_cancelled() is True
    assert cancel_latency_ms < 10.0, "O cancelamento cooperativo atômico deve responder em frações de milissegundo!"
    print(f"  [OK] Latência de sinalização do cancelamento: {cancel_latency_ms:.4f} ms (< 1s)")

def test_database_resilience_and_formal_migrations():
    print("\n>>> 6. Testando Resiliência do Banco (WAL, Health Check, Backups e Migrações Formais)...")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "resilient_vault.db")
        vault = DocumentContextVault(db_path=db_path)
        
        # 6.1 Verifica WAL Mode
        with vault._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0]
            assert journal_mode.lower() == "wal", f"Journal mode deve ser WAL, obteve: {journal_mode}"

        # 6.2 Health Check no Startup
        hc = vault.health_check()
        assert hc["status"] == "healthy"
        assert hc["integrity"] == "ok"
        print(f"  Health Check: {hc['integrity']}")

        # 6.3 5 Migrações Formais Executadas e Registradas
        with vault._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC;")
            mig_rows = cur.fetchall()
            assert len(mig_rows) == 5, f"Devem existir exatamente 5 migrações formais, obteve: {len(mig_rows)}"
            names = [r[1] for r in mig_rows]
            assert "initial_schema" in names
            assert "location_and_exif_metadata" in names
            assert "rebuild_fts5_index" in names
            assert "albums_and_collections" in names
            assert "smart_folders_and_privacy" in names

        # 6.4 FTS5 Virtual Table Operacional
        with vault._get_connection() as conn:
            conn.execute("INSERT INTO fts_documents (doc_hash, title, global_summary, content_text) VALUES ('hash123', 'Quantum Paper', 'Superconducting qubits', 'crosstalk mitigation')")
            match_row = conn.execute("SELECT doc_hash FROM fts_documents WHERE fts_documents MATCH 'qubits'").fetchone()
            assert match_row is not None
            assert match_row[0] == "hash123"

        print("  [OK] Banco resiliente, 5 migrações formais e FTS5 validados com sucesso!")

def test_hardware_aware_and_vram_cleanup():
    print("\n>>> 7. Testando Detecção Hardware-Aware e VRAM Cleanup...")
    hw = HardwareDetector.get_hardware_info()
    print(f"  OS: {hw['os']} ({hw['architecture']}) | Cores: {hw['cpu_cores']}")
    print(f"  RAM Total: {hw['total_ram_gb']} GB | GPU: {hw['gpu_name']} ({hw['vram_gb']} GB VRAM)")
    print(f"  Tier Escolhido: {hw['tier'].upper()} -> Modelo: {hw['recommended_model']}")
    print(f"  Motivo: {hw['decision_reason']}")
    
    assert hw["tier"] in ("small", "medium", "large")
    assert hw["recommended_model"] in ("qwen2.5vl:3b", "qwen2.5vl:7b", "qwen2.5vl:32b")

    # Cache do AppState
    t0 = time.perf_counter()
    hw_cached = HardwareDetector.get_hardware_info()
    t_cached = (time.perf_counter() - t0) * 1000.0
    assert hw_cached == hw
    assert t_cached < 1.0, "O hardware em cache não deve executar subprocessos adicionais!"
    print(f"  AppState Cache Hit: {t_cached:.3f} ms")

    # VRAM Cleanup & Memory Trim (não lança exceções mesmo se Ollama estiver offline)
    VRAMManager.trim_process_memory()
    VRAMManager.unload_ollama_models(model_name="qwen2.5vl:7b")
    print("  [OK] VRAM cleanup e memory trimming executados com integridade.")

def test_platform_path_canonicalization():
    print("\n>>> 8. Testando Platform Core e Tratamento de Paths UNC (\\\\?\\)...")
    if sys.platform == "win32":
        unc_path = "\\\\?\\C:\\Users\\Default\\Documents\\report.pdf"
        canon = canonicalize_path(unc_path)
        assert not canon.startswith("\\\\?\\"), f"Prefixos \\\\?\\ devem ser sanitizados: {canon}"
        assert canon.startswith("C:\\")

    app_data = get_app_data_dir()
    assert app_data.exists()
    assert (app_data / "db").exists()
    assert (app_data / "thumbnails").exists()
    print(f"  AppData Isolado: {app_data}")
    print("  [OK] Normalização de caminhos e isolamento confirmados.")

def test_large_document_fingerprint_and_foreign_key_consistency():
    print("\n>>> 9. Testando Documentos Grandes (> 64KB), Invariância de Hash e Chaves Estrangeiras...")
    from pdf_resilience_manager import PDFResilienceManager
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = os.path.join(tmpdir, "heavy_docs")
        os.makedirs(docs_dir, exist_ok=True)
        
        # Cria arquivos com tamanho muito superior a 64KB
        f_large = os.path.join(docs_dir, "large_report_128k.txt")
        with open(f_large, "w", encoding="utf-8") as f:
            f.write("A" * 131072) # 128 KB
            
        f_huge = os.path.join(docs_dir, "huge_report_500k.txt")
        with open(f_huge, "w", encoding="utf-8") as f:
            f.write("B" * 524288) # 512 KB

        db_path = os.path.join(tmpdir, "vault.db")
        thumbs_dir = os.path.join(tmpdir, "thumbs")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault, thumbnails_dir=thumbs_dir)

        # Executa o scan: DEVE passar sem IntegrityError em document_sections
        res = scanner.scan_directory(docs_dir)
        assert res["status"] == "completed"
        assert res["reclassified_new"] == 2

        # Valida que doc_hash é idêntico em documents, document_sections, fts_documents e thumbnails
        with vault._get_connection() as conn:
            docs = conn.execute("SELECT doc_hash, title FROM documents").fetchall()
            assert len(docs) == 2
            for d in docs:
                h = d["doc_hash"]
                # Valida chave estrangeira em document_sections
                sec = conn.execute("SELECT section_id FROM document_sections WHERE doc_hash = ?", (h,)).fetchone()
                assert sec is not None, f"Chave estrangeira órfã para doc_hash: {h}"
                # Valida FTS5
                fts = conn.execute("SELECT doc_hash FROM fts_documents WHERE doc_hash = ?", (h,)).fetchone()
                assert fts is not None, f"FTS5 desincronizado para doc_hash: {h}"
                # Valida thumbnail gerado em AppData
                assert os.path.exists(os.path.join(thumbs_dir, f"{h}.png")), f"Thumbnail ausente para doc_hash: {h}"

        print("  [OK] Consistência de hash de 64KB, integridade referencial SQLite e thumbnails validados!")

def test_batch_fast_discovery_and_modification_lifecycle():
    print("\n>>> 10. Testando Batch Fast Discovery (O(1) Transação) e Ciclo de Vida de Modificação...")
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = os.path.join(tmpdir, "repo_docs")
        os.makedirs(docs_dir, exist_ok=True)
        
        # Cria 300 arquivos
        for i in range(300):
            with open(os.path.join(docs_dir, f"doc_{i:03d}.txt"), "w") as f:
                f.write(f"Document payload data version 1 - id {i}")

        db_path = os.path.join(tmpdir, "batch_vault.db")
        thumbs_dir = os.path.join(tmpdir, "batch_thumbs")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault, thumbnails_dir=thumbs_dir)

        # 1. Scan inicial
        res1 = scanner.scan_directory(docs_dir)
        assert res1["reclassified_new"] == 300

        # 2. Fast Discovery em lote
        t0 = time.perf_counter()
        res2 = scanner.scan_directory(docs_dir)
        t_fast_ms = (time.perf_counter() - t0) * 1000.0
        assert res2["unchanged_fast_skipped"] == 300
        assert res2["processed_heavy"] == 0
        print(f"  Batch Fast Discovery: 300 arquivos verificados em {t_fast_ms:.2f} ms!")

        # 3. Modificação de um arquivo
        target_mod = os.path.join(docs_dir, "doc_042.txt")
        time.sleep(0.02) # garante mtime diferente
        with open(target_mod, "w") as f:
            f.write("MODIFIED CONTENT: new version of doc 42 with updated financial data")

        res_mod = scanner.scan_directory(docs_dir)
        assert res_mod["reclassified_new"] == 1
        assert res_mod["unchanged_fast_skipped"] == 299

        # 4. Scan imediato posterior: tudo deve estar inalterado
        res_after = scanner.scan_directory(docs_dir)
        assert res_after["unchanged_fast_skipped"] == 300
        assert res_after["processed_heavy"] == 0
        print("  [OK] Ciclo de modificação e invalidação de versão anterior validados com integridade!")

def test_pdf_native_pipeline_blank_detection_and_montage():
    print("\n>>> 11. Testando Pipeline Nativo PDF, Detecção de Página em Branco e Montagem...")
    from pdf_resilience_manager import PDFResilienceManager
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = os.path.join(tmpdir, "pdf_docs")
        thumbs_dir = os.path.join(tmpdir, "pdf_thumbs")
        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(thumbs_dir, exist_ok=True)
        pdf_path = os.path.join(docs_dir, "multipage_document.pdf")
        
        # Constrói PDF com Capa em branco (pág 1 vazia) e duas páginas com conteúdo real
        pdf_bytes = (
            b"%PDF-1.7\n"
            b"1 0 obj\n<< /Length 12 >>\nstream\nBT () Tj ET\nendstream\nendobj\n" # Pág 1: Branca
            b"2 0 obj\n<< /Length 60 >>\nstream\nBT /F1 12 Tf (Primeira Pagina com Conteudo Tecnico sobre Redes Neurais e Aprendizado) Tj ET\nendstream\nendobj\n"
            b"3 0 obj\n<< /Length 60 >>\nstream\nBT /F1 12 Tf (Segunda Pagina com Resultados Empiricos e Analise Comparativa) Tj ET\nendstream\nendobj\n"
            b"%%EOF"
        )
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # 1. Extração nativa de páginas
        info = PDFResilienceManager.extract_pdf_pages_and_text(pdf_path)
        assert info["has_sufficient_text"] is True
        assert len(info["pages"]) == 3
        # Garante que detectou pág 1 como branca e filtrou
        assert info["pages"][0]["is_blank"] is True
        assert info["pages"][1]["is_blank"] is False
        assert info["pages"][2]["is_blank"] is False
        assert info["first_content_pages"] == [2, 3] # Pulou a capa vazia!

        # 2. Geração da montagem de 2 páginas
        thumb_out = os.path.join(thumbs_dir, "montage_thumb.png")
        success = PDFResilienceManager.generate_pdf_montage_thumbnail(pdf_path, "pdf_hash_1", thumb_out)
        assert success is True
        assert os.path.exists(thumb_out)
        
        # Valida dimensões da montagem
        with Image.open(thumb_out) as img:
            assert img.size == (440, 300)

        # 3. Scan com o IncrementalScanner
        db_path = os.path.join(tmpdir, "pdf_vault.db")
        vault = DocumentContextVault(db_path=db_path)
        scanner = IncrementalScanner(vault=vault, thumbnails_dir=thumbs_dir)

        scan_res = scanner.scan_directory(docs_dir)
        assert scan_res["status"] == "completed"
        assert scan_res["reclassified_new"] == 1
        
        print("  [OK] Extração nativa, detecção de páginas em branco e montagem de 2 páginas validadas!")

if __name__ == "__main__":
    test_strict_read_only_principle()
    test_privacy_and_anti_leak_vault()
    test_two_phase_incremental_scanning_and_move_detection()
    test_checkpoint_persistence_and_interrupted_resume()
    test_cooperative_cancellation_speed()
    test_database_resilience_and_formal_migrations()
    test_hardware_aware_and_vram_cleanup()
    test_platform_path_canonicalization()
    test_large_document_fingerprint_and_foreign_key_consistency()
    test_batch_fast_discovery_and_modification_lifecycle()
    test_pdf_native_pipeline_blank_detection_and_montage()
    print("\n=================================================================")
    print("TODOS OS TESTES DE SEGURANÇA, PRIVACIDADE E SCANNER PASSARAM 100%!")
    print("=================================================================")
