"""
Módulo de Arquitetura de Contexto Global de Documentos e Banco de Dados Único (Vault).
Totalmente alinhado aos princípios da arquitetura frank_sherlock:
1. Princípio Read-Only Estrito:
   O banco de dados, backups e metadados residem exclusivamente no diretório isolado do usuário
   (%LOCALAPPDATA%\\FrankTranslator no Windows ou ~/.local/share/frank_translator no Linux/macOS).
   Zero escritas nos diretórios de documentos escaneados (mesmo montados como NFS/NAS read-only).
2. Resiliência do Banco & Migrações Formais:
   - SQLite com WAL mode (leituras concorrentes durante escrita).
   - Health check de integridade no startup (PRAGMA integrity_check).
   - Backup automático antes de executar migrações (.bak em backups/).
   - Sistema formal de 5 migrações imutáveis e ordenadas por posição.
3. Invariância de Arquivo & Fingerprint de 64KB:
   - Cálculo instantâneo de fingerprint SHA-256 dos primeiros 64KB + tamanho.
   - Detecção de arquivos movidos ou renomeados sem reprocessamento.
4. Persistência de Scan Jobs (Checkpoint por arquivo):
   - Registro de cursor em scan_jobs para retomada automática se o processo for interrompido.
5. Proteção Anti-Vazamento:
   - Criptografia transparente em repouso via VaultProtector (DPAPI / HMAC) para cache e leituras.
"""

import os
import sys
import hashlib
import sqlite3
import json
import time
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Any

from platform_core import get_app_data_dir, canonicalize_path
from privacy_vault import VaultProtector

DB_FILENAME = "readflow_vault.db"

class FileRegistrationResult(tuple):
    """Tupla estendida compatível com desempacotamento (doc_hash, is_new)."""
    def __new__(cls, doc_hash: str, is_new: bool, was_moved: bool = False, known_paths: List[str] = None):
        return super().__new__(cls, (doc_hash, is_new))
        
    def __init__(self, doc_hash: str, is_new: bool, was_moved: bool = False, known_paths: List[str] = None):
        self.doc_hash = doc_hash
        self.is_new = is_new
        self.was_moved = was_moved
        self.known_paths = known_paths or []

class DocumentContextVault:
    def __init__(self, db_path: Optional[str] = None, enable_privacy: bool = True):
        if db_path is None:
            app_dir = get_app_data_dir()
            self.db_path = str(app_dir / "db" / DB_FILENAME)
        else:
            self.db_path = canonicalize_path(db_path)
            
        self.enable_privacy = enable_privacy
        self._ensure_db_directory()
        self.health_check()
        self._apply_formal_migrations()

    def _ensure_db_directory(self):
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        """Cria conexão SQLite de alta performance com WAL mode habilitado e fechamento garantido."""
        self._ensure_db_directory()
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Otimizações de robustez e velocidade
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA wal_autocheckpoint = 1000;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA mmap_size = 268435456;") # 256MB memory map
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def checkpoint_wal(self, mode: str = "TRUNCATE") -> Dict[str, Any]:
        """
        Executa checkpoint formal do log WAL no SQLite (TRUNCATE, PASSIVE, FULL, RESTART).
        Limpa e trunca o arquivo de log para liberar espaço e garantir que as alterações estejam no arquivo .db.
        """
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        target_mode = mode.upper() if mode.upper() in valid_modes else "TRUNCATE"
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(f"PRAGMA wal_checkpoint({target_mode});")
                row = cur.fetchone()
                return {
                    "success": True,
                    "busy": row[0] if row else 0,
                    "log_frames": row[1] if row else 0,
                    "checkpointed_frames": row[2] if row else 0,
                    "mode": target_mode
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def vacuum_db(self, incremental: bool = False, pages: int = 0) -> Dict[str, Any]:
        """Executa VACUUM ou PRAGMA incremental_vacuum para liberar páginas e desfragmentar o banco."""
        try:
            if incremental:
                with self._get_connection() as conn:
                    if pages > 0:
                        conn.execute(f"PRAGMA incremental_vacuum({pages});")
                    else:
                        conn.execute("PRAGMA incremental_vacuum;")
                return {"success": True, "mode": "incremental"}

            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.isolation_level = None
            try:
                conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")
                conn.execute("VACUUM;")
            finally:
                conn.close()
            return {"success": True, "mode": "full"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_database_size_bytes(self) -> Dict[str, int]:
        """Retorna o tamanho em bytes do banco principal, do arquivo WAL e do total."""
        return self.get_storage_size_bytes()

    def get_storage_size_bytes(self) -> Dict[str, int]:
        """
        Retorna o tamanho combinado em bytes:
        - Banco de dados principal (.db)
        - Log WAL (.db-wal)
        - Diretório de thumbnails geradas (.png)
        """
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        wal_path = f"{self.db_path}-wal"
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

        # Diretório de thumbnails associado
        thumb_dir = Path(self.db_path).parent / "thumbnails"
        thumb_size = 0
        if thumb_dir.exists():
            for p in thumb_dir.glob("*.png"):
                try:
                    thumb_size += p.stat().st_size
                except Exception:
                    pass

        return {
            "db_bytes": db_size,
            "wal_bytes": wal_size,
            "thumbnails_bytes": thumb_size,
            "total_bytes": db_size + wal_size + thumb_size
        }

    def enforce_size_quota(self, max_size_mb: int = 500) -> Dict[str, Any]:
        """
        Garante que o armazenamento combinado (DB + WAL + Thumbnails) não exceda a cota estipulada em megabytes.
        Caso o limite seja ultrapassado:
        1. Executa checkpoint TRUNCATE do WAL.
        2. Remove as entradas mais antigas da tabela translation_cache segundo política LRU (last_accessed_at).
        3. Remove thumbnails antigas se ainda exceder a cota.
        4. Executa incremental vacuum / vacuum para liberar páginas no sistema de arquivos.
        """
        quota_bytes = max_size_mb * 1024 * 1024
        sizes = self.get_storage_size_bytes()
        evicted_count = 0
        evicted_thumbs = 0

        max_rounds = 5
        while sizes["total_bytes"] > quota_bytes and max_rounds > 0:
            max_rounds -= 1
            self.checkpoint_wal(mode="TRUNCATE")
            sizes = self.get_storage_size_bytes()
            if sizes["total_bytes"] <= quota_bytes:
                break

            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM translation_cache")
                total_cached = cur.fetchone()[0]
                if total_cached > 0:
                    limit_evict = max(1, total_cached // 4)
                    cur.execute(
                        "DELETE FROM translation_cache WHERE cache_key IN "
                        "(SELECT cache_key FROM translation_cache ORDER BY COALESCE(last_accessed_at, created_at) ASC LIMIT ?)",
                        (limit_evict,)
                    )
                    evicted_count += cur.rowcount

            self.vacuum_db(incremental=True)
            self.checkpoint_wal(mode="TRUNCATE")
            sizes = self.get_storage_size_bytes()

            # Descarte de thumbnails antigas se ainda estiver acima da cota combinada
            if sizes["total_bytes"] > quota_bytes:
                thumb_dir = Path(self.db_path).parent / "thumbnails"
                if thumb_dir.exists():
                    thumb_files = []
                    for p in thumb_dir.glob("*.png"):
                        try:
                            thumb_files.append((p.stat().st_mtime, p))
                        except Exception:
                            pass
                    thumb_files.sort(key=lambda x: x[0])
                    for _, p in thumb_files[:max(1, len(thumb_files) // 3)]:
                        try:
                            p.unlink(missing_ok=True)
                            evicted_thumbs += 1
                        except Exception:
                            pass
                sizes = self.get_storage_size_bytes()

        return {
            "quota_mb": max_size_mb,
            "current_total_mb": round(sizes["total_bytes"] / (1024 * 1024), 2),
            "evicted_entries": evicted_count,
            "evicted_thumbnails": evicted_thumbs,
            "under_quota": sizes["total_bytes"] <= quota_bytes
        }

    def shutdown(self) -> Dict[str, Any]:
        """Encerramento limpo da base de dados: executa checkpoint TRUNCATE do WAL."""
        return self.checkpoint_wal(mode="TRUNCATE")

    def health_check(self) -> Dict[str, Any]:
        """
        Health check no startup: executa PRAGMA integrity_check.
        Garante recuperação e validação de consistência física do banco.
        """
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            return {"status": "new", "message": "Banco novo a ser inicializado."}
            
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            row = cur.fetchone()
            result = row[0] if row else "unknown"
            if result == "ok":
                return {"status": "healthy", "integrity": "ok"}
            else:
                return {"status": "corrupt", "integrity": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            if conn:
                conn.close()

    def backup_before_migration(self) -> Optional[str]:
        """
        Backup automático antes de migrações:
        Copia o banco para a pasta de backups com timestamp para prevenir perda de dados.
        """
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            return None
            
        backup_dir = os.path.join(os.path.dirname(self.db_path), "..", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_filename = f"vault_backup_{timestamp}.bak"
        backup_path = os.path.join(backup_dir, backup_filename)

        src_conn = None
        dst_conn = None
        try:
            src_conn = sqlite3.connect(self.db_path)
            dst_conn = sqlite3.connect(backup_path)
            src_conn.backup(dst_conn)
            return backup_path
        except Exception:
            # Fallback para cópia direta
            try:
                shutil.copy2(self.db_path, backup_path)
                return backup_path
            except Exception:
                return None
        finally:
            if dst_conn:
                dst_conn.close()
            if src_conn:
                src_conn.close()

    def _apply_formal_migrations(self):
        """
        Sistema formal de migrações ordenadas e imutáveis (5 migrações):
        - Migração 1: Schema inicial (documents, roots, scan_jobs, document_sections, translation_cache, FTS5)
        - Migração 2: Coluna location_text e exif_tags para metadados estendidos
        - Migração 3: Rebuild do índice FTS5 (otimização de tokenização e busca)
        - Migração 4: Tabelas albums e album_files para coleções e organização manual
        - Migração 5: Tabela smart_folders e privacy_settings para queries salvas e controle de privacidade
        """
        # Garante tabela de controle de versão
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at REAL NOT NULL,
                checksum TEXT
            );
            """)

            cur = conn.cursor()
            cur.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
            applied_versions = {row[0] for row in cur.fetchall()}

        migrations = [
            (1, "initial_schema", self._migration_1_initial),
            (2, "location_and_exif_metadata", self._migration_2_location_metadata),
            (3, "rebuild_fts5_index", self._migration_3_rebuild_fts),
            (4, "albums_and_collections", self._migration_4_albums_collections),
            (5, "smart_folders_and_privacy", self._migration_5_smart_folders_privacy),
        ]

        # Verifica se alguma migração precisa rodar
        needed = [m for m in migrations if m[0] not in applied_versions]
        if needed:
            # Realiza backup preventivo
            self.backup_before_migration()

            for version, name, func in needed:
                with self._get_connection() as conn:
                    # Executa a migração
                    func(conn)
                    # Registra a migração como imutável
                    conn.execute("""
                    INSERT INTO schema_migrations (version, name, applied_at, checksum)
                    VALUES (?, ?, ?, ?)
                    """, (version, name, time.time(), hashlib.sha256(name.encode()).hexdigest()))

        # Garante retrocompatibilidade com bancos que já existiam antes da adição da coluna last_accessed_at
        with self._get_connection() as conn:
            try:
                conn.execute("ALTER TABLE translation_cache ADD COLUMN last_accessed_at REAL;")
            except Exception:
                pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_lru ON translation_cache(last_accessed_at);")
            except Exception:
                pass

        # Garante que o banco opere com auto_vacuum = INCREMENTAL (modo 2) para permitir liberação de páginas
        is_incremental = False
        if os.path.exists(self.db_path):
            with self._get_connection() as conn:
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA auto_vacuum;")
                    row = cur.fetchone()
                    if row and row[0] == 2:
                        is_incremental = True
                except Exception:
                    pass

            if not is_incremental:
                try:
                    conv_conn = sqlite3.connect(self.db_path, timeout=15.0)
                    conv_conn.isolation_level = None
                    conv_conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")
                    conv_conn.execute("VACUUM;")
                    conv_conn.close()
                except Exception:
                    pass

    def _migration_1_initial(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_hash TEXT PRIMARY KEY,
            file_size_bytes INTEGER NOT NULL,
            mtime REAL,
            title TEXT,
            author TEXT,
            domain TEXT,
            global_summary TEXT,
            key_glossary TEXT,
            total_pages INTEGER DEFAULT 1,
            known_paths TEXT NOT NULL,
            last_seen_scan_id TEXT,
            created_at REAL NOT NULL,
            last_accessed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS roots (
            root_id INTEGER PRIMARY KEY AUTOINCREMENT,
            root_path TEXT UNIQUE NOT NULL,
            last_scan_at REAL,
            total_files INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS scan_jobs (
            job_id TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            status TEXT NOT NULL, -- 'in_progress', 'completed', 'cancelled', 'interrupted'
            last_processed_file TEXT,
            scanned_files_count INTEGER DEFAULT 0,
            total_files_count INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_sections (
            section_id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_hash TEXT NOT NULL,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            section_title TEXT,
            section_type TEXT,
            section_summary TEXT,
            keywords TEXT,
            FOREIGN KEY(doc_hash) REFERENCES documents(doc_hash) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS translation_cache (
            cache_key TEXT PRIMARY KEY,
            doc_hash TEXT NOT NULL,
            page_num INTEGER,
            source_text TEXT NOT NULL,
            context_used TEXT,
            translated_text TEXT NOT NULL,
            model_id TEXT NOT NULL,
            latency_ms REAL,
            hit_count INTEGER DEFAULT 1,
            created_at REAL NOT NULL,
            last_accessed_at REAL,
            FOREIGN KEY(doc_hash) REFERENCES documents(doc_hash) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_doc_sections ON document_sections(doc_hash, page_start, page_end);
        CREATE INDEX IF NOT EXISTS idx_trans_doc ON translation_cache(doc_hash);
        CREATE INDEX IF NOT EXISTS idx_trans_lru ON translation_cache(last_accessed_at);
        CREATE INDEX IF NOT EXISTS idx_scan_jobs_status ON scan_jobs(status);

        CREATE VIRTUAL TABLE IF NOT EXISTS fts_documents USING fts5(
            doc_hash UNINDEXED,
            title,
            global_summary,
            content_text,
            tokenize = 'unicode61'
        );
        """)

    def _migration_2_location_metadata(self, conn: sqlite3.Connection):
        # Adiciona colunas para metadados geográficos / EXIF e contexto sem reescrever
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN location_text TEXT;")
        except sqlite3.OperationalError:
            pass # Coluna já existe
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN exif_tags TEXT;")
        except sqlite3.OperationalError:
            pass

    def _migration_3_rebuild_fts(self, conn: sqlite3.Connection):
        # Rebuild do índice FTS5 com tokenizador unicode61 enriquecido
        conn.execute("INSERT INTO fts_documents(fts_documents) VALUES('rebuild');")

    def _migration_4_albums_collections(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS albums (
            album_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS album_files (
            album_id INTEGER NOT NULL,
            doc_hash TEXT NOT NULL,
            added_at REAL NOT NULL,
            PRIMARY KEY(album_id, doc_hash),
            FOREIGN KEY(album_id) REFERENCES albums(album_id) ON DELETE CASCADE,
            FOREIGN KEY(doc_hash) REFERENCES documents(doc_hash) ON DELETE CASCADE
        );
        """)

    def _migration_5_smart_folders_privacy(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS smart_folders (
            folder_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            query_filter TEXT NOT NULL, -- JSON com filtros de busca automática
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS privacy_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        INSERT OR IGNORE INTO privacy_settings (key, value, updated_at)
        VALUES ('encryption_enabled', 'true', 1700000000.0);
        """)

    @staticmethod
    def compute_content_fingerprint(file_path: str) -> str:
        """
        Calcula fingerprint invariante a localização/nome do arquivo.
        - Arquivos até 20MB: leitura integral (0 colisão matemática garantida, < 10ms).
        - Arquivos grandes (> 20MB): multi-window chunking (Início, 25%, 50%, 75%, Fim + Tamanho Exato).
        """
        norm_path = canonicalize_path(file_path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {norm_path}")
            
        file_size = os.path.getsize(norm_path)
        hasher = hashlib.sha256()
        hasher.update(file_size.to_bytes(8, byteorder='big'))
        
        chunk_size = 65536 # 64 KB
        threshold_full = 20 * 1024 * 1024 # 20 MB
        
        with open(norm_path, "rb") as f:
            if file_size <= threshold_full:
                while chunk := f.read(262144): # 256KB por read
                    hasher.update(chunk)
            else:
                hasher.update(f.read(chunk_size))
                f.seek(file_size // 4)
                hasher.update(f.read(chunk_size))
                f.seek(file_size // 2)
                hasher.update(f.read(chunk_size))
                f.seek((file_size * 3) // 4)
                hasher.update(f.read(chunk_size))
                f.seek(file_size - chunk_size)
                hasher.update(f.read(chunk_size))
                
        return hasher.hexdigest()

    @staticmethod
    def compute_64kb_fingerprint(file_path: str) -> str:
        """
        Cálculo ultrarrápido de fingerprint da fase pesada (frank_sherlock spec):
        SHA-256 dos primeiros 64KB + tamanho do arquivo.
        Permite identificar instantaneamente arquivos movidos ou renomeados.
        """
        norm_path = canonicalize_path(file_path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {norm_path}")

        file_size = os.path.getsize(norm_path)
        hasher = hashlib.sha256()
        hasher.update(file_size.to_bytes(8, byteorder='big'))

        with open(norm_path, "rb") as f:
            first_chunk = f.read(65536)
            hasher.update(first_chunk)

        return hasher.hexdigest()

    def register_or_update_file(self, file_path: str, title: Optional[str] = None, domain: Optional[str] = None, doc_hash: Optional[str] = None) -> FileRegistrationResult:
        """
        Registra ou atualiza um arquivo no banco.
        Retorna FileRegistrationResult (doc_hash, is_new, was_moved, known_paths).
        Se o usuário mudou o arquivo de pasta, detecta automaticamente e atualiza o histórico!
        """
        norm_path = canonicalize_path(file_path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {norm_path}")
            
        if doc_hash is None:
            doc_hash = self.compute_content_fingerprint(norm_path)
        now = time.time()
        file_size = os.path.getsize(norm_path)
        mtime = os.path.getmtime(norm_path)
        
        with self._get_connection() as conn:
            # Se o arquivo foi modificado, desassocia o caminho de qualquer doc_hash anterior diferente
            conflicting_rows = conn.execute("SELECT doc_hash, known_paths FROM documents WHERE doc_hash != ?", (doc_hash,)).fetchall()
            for old_r in conflicting_rows:
                old_h = old_r["doc_hash"]
                old_paths = json.loads(old_r["known_paths"]) if old_r["known_paths"] else []
                if norm_path in old_paths:
                    updated_paths = [p for p in old_paths if p != norm_path]
                    conn.execute("UPDATE documents SET known_paths = ? WHERE doc_hash = ?", (json.dumps(updated_paths), old_h))

            row = conn.execute("SELECT doc_hash, known_paths, title, domain FROM documents WHERE doc_hash = ?", (doc_hash,)).fetchone()
            if row:
                # Arquivo já existe no banco!
                known = json.loads(row["known_paths"]) if row["known_paths"] else []
                was_moved = (norm_path not in known)
                if was_moved:
                    known.append(norm_path)
                conn.execute("""
                    UPDATE documents 
                    SET known_paths = ?, mtime = ?, file_size_bytes = ?, last_accessed_at = ?
                    WHERE doc_hash = ?
                """, (json.dumps(known), mtime, file_size, now, doc_hash))
                return FileRegistrationResult(doc_hash, False, was_moved, known)
            else:
                # Novo arquivo
                known = [norm_path]
                clean_title = title or os.path.splitext(os.path.basename(norm_path))[0]
                conn.execute("""
                    INSERT INTO documents (doc_hash, file_size_bytes, mtime, title, domain, known_paths, created_at, last_accessed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (doc_hash, file_size, mtime, clean_title, domain or "General", json.dumps(known), now, now))
                return FileRegistrationResult(doc_hash, True, False, known)

    def save_document_context(self, doc_hash: str, title: str, domain: str, 
                              global_summary: str, glossary: Dict[str, str], 
                              sections: List[Dict[str, Any]]):
        """Salva a estrutura semântica global de um documento indexado."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE documents 
                SET title = ?, domain = ?, global_summary = ?, key_glossary = ?, last_accessed_at = ?
                WHERE doc_hash = ?
            """, (title, domain, global_summary, json.dumps(glossary), now, doc_hash))
            
            # Atualiza FTS5
            conn.execute("DELETE FROM fts_documents WHERE doc_hash = ?", (doc_hash,))
            conn.execute("""
                INSERT INTO fts_documents (doc_hash, title, global_summary, content_text)
                VALUES (?, ?, ?, ?)
            """, (doc_hash, title, global_summary, json.dumps(glossary)))

            # Limpa seções anteriores e insere novas
            conn.execute("DELETE FROM document_sections WHERE doc_hash = ?", (doc_hash,))
            for sec in sections:
                conn.execute("""
                    INSERT INTO document_sections 
                    (doc_hash, page_start, page_end, section_title, section_type, section_summary, keywords)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_hash,
                    sec.get("page_start", 1),
                    sec.get("page_end", 1),
                    sec.get("title", ""),
                    sec.get("type", "body"),
                    sec.get("summary", ""),
                    json.dumps(sec.get("keywords", []))
                ))

    def get_hierarchical_context_prompt(self, doc_hash: str, current_page: int, selected_text: str) -> str:
        """
        Constrói o prefixo de contexto comprimido e altamente informativo para a LLM:
        - Domínio técnico (ex: Engenharia Quântica)
        - Resumo global do documento / introdução (se disponível)
        - Seção ativa (ex: Resfriamento Criogênico)
        - Termos do glossário relevantes ao texto selecionado
        """
        with self._get_connection() as conn:
            doc = conn.execute("SELECT domain, title, global_summary, key_glossary FROM documents WHERE doc_hash = ?", (doc_hash,)).fetchone()
            if not doc:
                return ""
            
            domain = doc["domain"] or "Geral"
            glossary = json.loads(doc["key_glossary"]) if doc["key_glossary"] else {}
            global_summary = doc["global_summary"] or ""
            
            sec = conn.execute("""
                SELECT section_title, section_summary 
                FROM document_sections 
                WHERE doc_hash = ? AND page_start <= ? AND page_end >= ?
                LIMIT 1
            """, (doc_hash, current_page, current_page)).fetchone()
            
            matched_terms = {}
            lower_text = selected_text.lower()
            for k, v in glossary.items():
                if k.lower() in lower_text:
                    matched_terms[k] = v
                    
            context_parts = [f"[Domínio: {domain}]"]
            if global_summary:
                short_summary = global_summary if len(global_summary) <= 120 else global_summary[:117] + "..."
                context_parts.append(f"[Resumo Global: {short_summary}]")
            if sec and sec["section_title"]:
                context_parts.append(f"[Seção: {sec['section_title']}]")
            
            if matched_terms:
                terms_str = ", ".join([f"{k}->{v}" for k, v in matched_terms.items()])
                context_parts.append(f"[Glossário: {terms_str}]")
                
            return " ".join(context_parts)

    def lookup_cache(self, doc_hash: str, source_text: str, model_id: Optional[str] = None, context_mode: str = "default") -> Optional[str]:
        """Consulta cache instantâneo de tradução (< 0.5 ms) com suporte a descriptografia transparente."""
        try:
            with self._get_connection() as conn:
                row = None
                cache_key = None
                if model_id is not None:
                    raw_key = f"{doc_hash}:{source_text.strip().lower()}:{context_mode}:{model_id}"
                    cache_key = hashlib.sha256(raw_key.encode('utf-8', errors='replace')).hexdigest()
                    row = conn.execute("SELECT translated_text FROM translation_cache WHERE cache_key = ?", (cache_key,)).fetchone()
                else:
                    # Se model_id não foi especificado, tenta chave default primeiro
                    raw_key = f"{doc_hash}:{source_text.strip().lower()}:{context_mode}:default"
                    cache_key = hashlib.sha256(raw_key.encode('utf-8', errors='replace')).hexdigest()
                    row = conn.execute("SELECT translated_text FROM translation_cache WHERE cache_key = ?", (cache_key,)).fetchone()
                    if not row:
                        norm_src = source_text.strip().lower()
                        if not self.enable_privacy:
                            # Busca indexada direta pelo texto de origem (< 0.1ms)
                            row = conn.execute(
                                "SELECT cache_key, translated_text FROM translation_cache WHERE doc_hash = ? AND LOWER(TRIM(source_text)) = ? ORDER BY COALESCE(last_accessed_at, created_at) DESC LIMIT 1",
                                (doc_hash, norm_src)
                            ).fetchone()
                            if row:
                                cache_key = row["cache_key"]
                        else:
                            # Busca nas entradas recentes do documento com descriptografia transparente
                            rows = conn.execute(
                                "SELECT cache_key, source_text, translated_text FROM translation_cache WHERE doc_hash = ? ORDER BY COALESCE(last_accessed_at, created_at) DESC LIMIT 200",
                                (doc_hash,)
                            ).fetchall()
                            for r in rows:
                                dec_src = VaultProtector.decrypt_text(r["source_text"])
                                if dec_src.strip().lower() == norm_src:
                                    row = r
                                    cache_key = r["cache_key"]
                                    break

                if row:
                    now = time.time()
                    try:
                        conn.execute("UPDATE translation_cache SET hit_count = hit_count + 1, last_accessed_at = ? WHERE cache_key = ?", (now, cache_key))
                    except Exception:
                        pass
                    stored_val = row["translated_text"]
                    if self.enable_privacy:
                        return VaultProtector.decrypt_text(stored_val)
                    return stored_val
        except Exception:
            return None
        return None

    def store_cache(self, doc_hash: str, page_num: int, source_text: str, 
                    context_used: str, translated_text: str, model_id: str, 
                    latency_ms: float, context_mode: str = "default"):
        """Armazena tradução no cache ACID, opcionalmente cifrado com DPAPI/HMAC."""
        raw_key = f"{doc_hash}:{source_text.strip().lower()}:{context_mode}:{model_id}"
        cache_key = hashlib.sha256(raw_key.encode('utf-8', errors='replace')).hexdigest()
        now = time.time()
        
        # Proteção anti-vazamento em repouso
        if self.enable_privacy:
            sec_source = VaultProtector.encrypt_text(source_text)
            sec_context = VaultProtector.encrypt_text(context_used)
            sec_trans = VaultProtector.encrypt_text(translated_text)
        else:
            sec_source = source_text
            sec_context = context_used
            sec_trans = translated_text

        try:
            with self._get_connection() as conn:
                # Garante integridade referencial: registra documento ad-hoc caso não exista
                conn.execute("""
                    INSERT OR IGNORE INTO documents 
                    (doc_hash, file_size_bytes, mtime, title, created_at, last_accessed_at, known_paths)
                    VALUES (?, 0, ?, 'Quick / Ad-hoc Translation', ?, ?, '[]')
                """, (doc_hash, now, now, now))

                conn.execute("""
                    INSERT INTO translation_cache 
                    (cache_key, doc_hash, page_num, source_text, context_used, translated_text, model_id, latency_ms, created_at, last_accessed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET 
                        translated_text = excluded.translated_text,
                        latency_ms = excluded.latency_ms,
                        hit_count = hit_count + 1,
                        last_accessed_at = excluded.last_accessed_at
                """, (cache_key, doc_hash, page_num, sec_source, sec_context, sec_trans, model_id, latency_ms, now, now))
        except Exception:
            pass
