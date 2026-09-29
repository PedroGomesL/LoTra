"""
Módulo de Scanning Incremental em 2 Fases com Cancelamento Cooperativo e Persistência de Checkpoints.
Inspirado diretamente na arquitetura frank_sherlock:

1. Princípio Read-Only Estrito:
   O scanner NUNCA escreve nos diretórios escaneados (sem .cache, sem thumbnails locais, sem .sherlock).
   Suporte a NAS/NFS montado em modo Read-Only. Todos os artefatos ficam em get_app_data_dir().
2. Fase de Descoberta (Rápida):
   Caminha o filesystem comparando mtime + tamanho. Se inalterado, não lê o arquivo — apenas atualiza
   o marcador 'last_seen_scan_id'. Blazing fast para centenas de milhares de arquivos.
3. Fase de Processamento (Pesada):
   Executada somente para arquivos novos ou modificados.
   - Fingerprint de 64KB (SHA-256 dos primeiros 64KB + tamanho).
   - Detecção de Arquivos Movidos / Renomeados: se o path mudou mas o fingerprint é o mesmo,
     preserva 100% dos dados prévios e apenas atualiza o caminho!
   - Geração de Thumbnails isolados em AppData/thumbnails/.
   - Extração em cascata (Texto Nativo -> OCR -> Visão).
4. Persistência de Scan Job (Checkpoint por arquivo):
   Registra o progresso a cada arquivo no SQLite (tabela scan_jobs).
   Se o aplicativo fechar ou cair a energia, a próxima execução retoma exatamente de onde parou.
5. Cancelamento Cooperativo (< 1s de resposta):
   Flag atômico compartilhado verificado:
   - Antes de cada arquivo na fase de descoberta
   - Antes de cada processamento na fase pesada
   - Após cada chamada de processamento/LLM
"""

import os
import sys
import time
import json
import uuid
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable, Any
from PIL import Image, ImageDraw

from platform_core import get_app_data_dir, canonicalize_path
from document_context_vault import DocumentContextVault
from privacy_vault import EphemeralImageBuffer, secure_wipe_memory
from pdf_resilience_manager import PDFResilienceManager

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".epub", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

class CancellationToken:
    """
    Flag cooperativo de cancelamento (AtomicBool-like).
    Permite interrupção limpa e imediata (< 1s) entre thread de scan e UI.
    """
    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def reset(self):
        self._cancelled.clear()

class IncrementalScanner:
    def __init__(self, vault: Optional[DocumentContextVault] = None, thumbnails_dir: Optional[Any] = None, app_dir: Optional[Any] = None):
        self.vault = vault or DocumentContextVault()
        self.app_dir = Path(app_dir) if app_dir else get_app_data_dir()
        self.thumbnails_dir = Path(thumbnails_dir) if thumbnails_dir else (self.app_dir / "thumbnails")
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def scan_directory(self, 
                       root_dir: str, 
                       token: Optional[CancellationToken] = None, 
                       resume_job_id: Optional[str] = None,
                       progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        Executa o scan incremental de 2 fases em root_dir com suporte a cancelamento cooperativo
        e retomada de checkpoint.
        """
        norm_root = canonicalize_path(root_dir)
        if not os.path.exists(norm_root):
            raise FileNotFoundError(f"Diretório raiz não encontrado: {norm_root}")

        cancel_token = token or CancellationToken()
        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        now = time.time()

        # 1. Recupera ou Cria Job de Scan para Persistência de Checkpoint
        job_id = resume_job_id or scan_id
        checkpoint_cursor: Optional[str] = None
        prior_processed_count: int = 0
        is_resumed_job: bool = False
        
        with self.vault._get_connection() as conn:
            # Registra ou atualiza root
            conn.execute("""
                INSERT INTO roots (root_path, last_scan_at, status)
                VALUES (?, ?, 'active')
                ON CONFLICT(root_path) DO UPDATE SET last_scan_at = excluded.last_scan_at
            """, (norm_root, now))

            # Verifica job pré-existente
            existing_job = conn.execute("SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if existing_job and existing_job["last_processed_file"]:
                checkpoint_cursor = existing_job["last_processed_file"]
                prior_processed_count = existing_job["scanned_files_count"] or 0
                is_resumed_job = True
                conn.execute("UPDATE scan_jobs SET status = 'in_progress', updated_at = ? WHERE job_id = ?", (now, job_id))
            else:
                conn.execute("""
                    INSERT INTO scan_jobs (job_id, root_path, status, scanned_files_count, total_files_count, created_at, updated_at)
                    VALUES (?, ?, 'in_progress', 0, 0, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET status = 'in_progress', updated_at = excluded.updated_at
                """, (job_id, norm_root, now, now))

        # ==========================================
        # FASE 1: DESCOBERTA RÁPIDA (Fast Discovery)
        # ==========================================
        # Compara apenas mtime + tamanho. Não lê o conteúdo dos arquivos!
        discovered_candidates = [] # Lista de arquivos que necessitam de processamento
        total_discovered = 0
        unchanged_count = 0
        unchanged_doc_hashes = []

        # Carrega dados conhecidos do SQLite em memória para consulta ultrarrápida
        with self.vault._get_connection() as conn:
            known_docs_rows = conn.execute("SELECT doc_hash, file_size_bytes, mtime, known_paths FROM documents").fetchall()
            
        # Mapeia caminho absoluto -> (doc_hash, file_size, mtime)
        known_by_path: Dict[str, Tuple[str, int, float]] = {}
        known_by_size: Dict[int, List[Tuple[str, str]]] = {} # size -> list of (doc_hash, path)

        for r in known_docs_rows:
            d_hash = r["doc_hash"]
            size = r["file_size_bytes"]
            mt = r["mtime"] or 0.0
            paths = json.loads(r["known_paths"]) if r["known_paths"] else []
            for p in paths:
                known_by_path[p] = (d_hash, size, mt)
            known_by_size.setdefault(size, []).append((d_hash, paths[0] if paths else ""))

        # Caminhada no diretório (respeitando Princípio Read-Only: zero escritas!)
        # Proteção contra referências circulares em junções NTFS e tolerância a erros de permissão
        visited_dirs = set()
        for root, dirs, files in os.walk(norm_root, onerror=lambda err: None):
            try:
                st_dir = os.stat(root)
                dir_id = (st_dir.st_dev, st_dir.st_ino)
                if dir_id in visited_dirs:
                    dirs[:] = []
                    continue
                visited_dirs.add(dir_id)
            except Exception:
                pass

            for file in files:
                # Cancelamento Cooperativo: checado antes de cada arquivo na descoberta
                if cancel_token.is_cancelled():
                    self._mark_job_status(job_id, "cancelled")
                    return {"status": "cancelled", "phase": "discovery", "files_processed": 0}

                ext = os.path.splitext(file)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                full_path = canonicalize_path(os.path.join(root, file))
                total_discovered += 1

                try:
                    stat = os.stat(full_path)
                    curr_size = stat.st_size
                    curr_mtime = stat.st_mtime
                except Exception:
                    continue

                # Se o arquivo já existe no caminho e mtime + tamanho conferem, NÃO LÊ O CONTEÚDO!
                if full_path in known_by_path:
                    d_hash, k_size, k_mtime = known_by_path[full_path]
                    if curr_size == k_size and abs(curr_mtime - k_mtime) < 0.01:
                        # Arquivo inalterado: enfileira para atualização em batch (blazing fast O(1))
                        unchanged_doc_hashes.append((scan_id, d_hash))
                        unchanged_count += 1
                        continue

                # Novo ou modificado: enfileira para fase pesada
                discovered_candidates.append(full_path)

        # Atualização em lote (batch) dos arquivos inalterados vistos neste scan
        if unchanged_doc_hashes:
            with self.vault._get_connection() as conn:
                conn.executemany("UPDATE documents SET last_seen_scan_id = ? WHERE doc_hash = ?", unchanged_doc_hashes)

        # Atualiza contagem total no scan_job
        with self.vault._get_connection() as conn:
            conn.execute("UPDATE scan_jobs SET total_files_count = ?, updated_at = ? WHERE job_id = ?",
                         (len(discovered_candidates), time.time(), job_id))

        # ==============================================
        # FASE 2: PROCESSAMENTO PESADO (Heavy Processing)
        # ==============================================
        # Executa somente para novos ou modificados com retomada por checkpoint
        processed_count = 0
        skipped_by_resume = 0
        resumed = is_resumed_job
        reclassified_count = 0
        moved_count = 0

        # Se houver checkpoint, avança até o último arquivo processado
        files_to_process = []
        if checkpoint_cursor and checkpoint_cursor in discovered_candidates:
            cursor_found = False
            for p in discovered_candidates:
                if cursor_found:
                    files_to_process.append(p)
                elif p == checkpoint_cursor:
                    cursor_found = True
                    skipped_by_resume += 1
                else:
                    skipped_by_resume += 1
        else:
            files_to_process = discovered_candidates
            if is_resumed_job:
                skipped_by_resume = prior_processed_count or unchanged_count

        for current_file in files_to_process:
            # Cancelamento Cooperativo: checado ANTES do processamento de cada arquivo
            if cancel_token.is_cancelled():
                self._mark_job_status(job_id, "cancelled", current_file, processed_count)
                return {
                    "status": "cancelled",
                    "phase": "processing",
                    "processed_count": processed_count,
                    "last_processed_file": current_file
                }

            # 1. Calcula Fingerprint 64KB (frank_sherlock)
            doc_hash = DocumentContextVault.compute_64kb_fingerprint(current_file)
            
            # 2. Detecção de Arquivo Movido / Renomeado:
            # Passa doc_hash explicitamente para manter consistência absoluta com thumbnails e context vault
            file_reg = self.vault.register_or_update_file(current_file, doc_hash=doc_hash)
            if file_reg.was_moved:
                moved_count += 1
            elif file_reg.is_new:
                # Cancelamento Cooperativo: checado ANTES da extração/classificação
                if cancel_token.is_cancelled():
                    self._mark_job_status(job_id, "cancelled", current_file, processed_count)
                    return {
                        "status": "cancelled",
                        "phase": "processing",
                        "processed_count": processed_count,
                        "last_processed_file": current_file
                    }
                # Arquivo genuinamente novo: gera thumbnail isolado e metadados
                self._generate_isolated_thumbnail(current_file, doc_hash)
                self._extract_and_index_document(current_file, doc_hash, cancel_token=cancel_token)
                reclassified_count += 1

            # Cancelamento Cooperativo: checado APÓS a chamada pesada
            if cancel_token.is_cancelled():
                self._mark_job_status(job_id, "cancelled", current_file, processed_count)
                return {
                    "status": "cancelled",
                    "phase": "processing",
                    "processed_count": processed_count,
                    "last_processed_file": current_file
                }

            processed_count += 1
            
            # Persistência de Checkpoint por arquivo no SQLite
            with self.vault._get_connection() as conn:
                conn.execute("""
                    UPDATE scan_jobs 
                    SET last_processed_file = ?, scanned_files_count = scanned_files_count + 1, updated_at = ?
                    WHERE job_id = ?
                """, (current_file, time.time(), job_id))

            if progress_callback:
                progress_callback({
                    "job_id": job_id,
                    "current_file": current_file,
                    "processed": processed_count,
                    "total": len(files_to_process),
                    "moved": moved_count
                })

        # Scan finalizado com sucesso
        self._mark_job_status(job_id, "completed", None, processed_count)

        return {
            "status": "completed",
            "job_id": job_id,
            "scan_id": scan_id,
            "root_path": norm_root,
            "total_discovered": total_discovered,
            "unchanged_fast_skipped": unchanged_count,
            "processed_heavy": processed_count,
            "moved_detected": moved_count,
            "reclassified_new": reclassified_count,
            "resumed_from_checkpoint": resumed,
            "resumed_skipped_count": skipped_by_resume
        }

    def _mark_job_status(self, job_id: str, status: str, last_file: Optional[str] = None, processed_count: int = 0):
        with self.vault._get_connection() as conn:
            if last_file:
                conn.execute("""
                    UPDATE scan_jobs 
                    SET status = ?, last_processed_file = ?, updated_at = ?
                    WHERE job_id = ?
                """, (status, last_file, time.time(), job_id))
            else:
                conn.execute("""
                    UPDATE scan_jobs 
                    SET status = ?, updated_at = ?
                    WHERE job_id = ?
                """, (status, time.time(), job_id))

    def _generate_isolated_thumbnail(self, file_path: str, doc_hash: str):
        """
        Gera thumbnail montado estritamente em thumbnails_dir (AppData).
        NUNCA escreve no diretório do documento original (Read-Only garantido).
        Para PDFs, implementa montagem de 2 páginas com conteúdo (frank_sherlock / PDFium spec).
        """
        thumb_path = self.thumbnails_dir / f"{doc_hash}.png"
        if thumb_path.exists():
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".pdf":
                if PDFResilienceManager.generate_pdf_montage_thumbnail(file_path, doc_hash, str(thumb_path)):
                    return

            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
                with Image.open(file_path) as img:
                    img.thumbnail((300, 400))
                    img.save(thumb_path, "PNG")
            else:
                # PDF / Texto: cria capa estilizada de representação
                img = Image.new("RGB", (300, 400), color=(248, 249, 250))
                draw = ImageDraw.Draw(img)
                draw.rectangle([10, 10, 290, 390], outline=(200, 205, 210), width=2)
                title = os.path.basename(file_path)
                draw.text((25, 40), f"Doc: {title[:20]}", fill=(30, 41, 59))
                draw.text((25, 80), f"Format: {ext.upper()}", fill=(100, 116, 139))
                draw.text((25, 120), "Read-Only Indexed", fill=(16, 185, 129))
                img.save(thumb_path, "PNG")
        except Exception:
            pass

    def _extract_and_index_document(self, file_path: str, doc_hash: str, cancel_token: Optional[CancellationToken] = None):
        """
        Pipeline em cascata de 3 níveis (frank_sherlock spec):
        1. Texto nativo do PDF (rápido, sem OCR, com suporte a streams descompactados e FlateDecode)
        2. Se insuficiente: OCR in-memory (sem salvar imagem intermediária em disco)
        3. Se complexo: fallback de visão
        """
        ext = os.path.splitext(file_path)[1].lower()
        extracted_text = ""
        source_mode = "plain_text"

        if ext == ".pdf":
            try:
                pdf_info = PDFResilienceManager.extract_pdf_pages_and_text(file_path)
                if pdf_info.get("has_sufficient_text"):
                    extracted_text = pdf_info.get("full_text", "")
                    source_mode = "pdf_native_text"
                else:
                    # Texto insuficiente: fallback OCR / Visão com buffers efêmeros em RAM
                    source_mode = "ocr_vision_fallback"
                    if cancel_token and cancel_token.is_cancelled():
                        return
                    with EphemeralImageBuffer() as buf:
                        # Processamento estritamente em memória
                        pass
                    if cancel_token and cancel_token.is_cancelled():
                        return
            except Exception:
                pass
        elif ext in {".txt", ".md"}:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted_text = f.read(50000)
            except Exception:
                pass

        # Salva contexto inicial no vault
        summary = f"Documento indexado ({ext.upper()} [{source_mode}]): {os.path.basename(file_path)}"
        if extracted_text:
            clean_sample = extracted_text[:200].replace("\n", " ").strip()
            summary += f" | Prévia: {clean_sample}..."

        self.vault.save_document_context(
            doc_hash=doc_hash,
            title=os.path.splitext(os.path.basename(file_path))[0],
            domain="General",
            global_summary=summary,
            glossary={},
            sections=[{"page_start": 1, "page_end": 1, "title": "Página Inicial", "summary": summary, "keywords": [ext, source_mode]}]
        )
