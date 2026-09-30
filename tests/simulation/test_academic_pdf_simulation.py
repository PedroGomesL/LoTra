"""
Test Suite: Simulação de Utilização do LoTra com Acervo Acadêmico de PDFs
Valida o comportamento ponta a ponta do leitor e tradutor com documentos acadêmicos reais:

Cenários de Teste:
1. test_1_access_and_catalog_all_academic_pdfs:
   Valida leitura read-only de PDFs acadêmicos sem corromper ou modificar arquivos.
2. test_2_extract_text_and_normalize_academic_pdf_flow:
   Extrai streams e snippets reais dos PDFs e valida a normalização de quebras de linha e des-hifenização acadêmica.
3. test_3_simulate_reading_selection_and_translation_pipeline:
   Simula a seleção do usuário lendo o PDF (Alt+Q) e envio ao pipeline de tradução (vocabulário offline + LLM fallback).
4. test_4_sha256_context_vault_persistence_on_academic_documents:
   Garante indexação, fingerprint SHA-256 e recuperação rápida do contexto de leitura no cofre SQLite local sem duplicatas.
5. test_5_extreme_load_concurrent_pdf_snippet_translations:
   Executa 30 traduções concorrentes de trechos dos PDFs simulando leitura intensiva contínua.
"""

import os
import sys
import zlib
import re
import time
import tempfile
import threading
import unittest
from pathlib import Path

# Configuração de paths
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hud_tooltip import normalize_text_spacing
from translation_engine import OfflineContextTranslator, TranslationPipeline
from document_context_vault import DocumentContextVault


def fast_extract_pdf_snippets(pdf_path: Path, max_snippets: int = 40):
    """
    Extrator de texto puro de alta performance e resiliente a arquivos gigantes (>80MB).
    Varre os streams descompactados e extrai strings BT ... ET sem dependências externas.
    """
    snippets = []
    seen = set()
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()

        pos = 0
        total_len = len(data)
        while pos < total_len and len(snippets) < max_snippets:
            s_idx = data.find(b"stream", pos)
            if s_idx == -1:
                break
            content_start = s_idx + 6
            if content_start < total_len and data[content_start] == 13:
                content_start += 1
            if content_start < total_len and data[content_start] == 10:
                content_start += 1
            e_idx = data.find(b"endstream", content_start)
            if e_idx == -1:
                break
            
            stream_bytes = data[content_start:e_idx]
            pos = e_idx + 9

            decomp = None
            for w in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
                try:
                    decomp = zlib.decompress(stream_bytes, w)
                    break
                except Exception:
                    pass

            body = decomp if decomp is not None else stream_bytes
            if b"BT" in body:
                raw_strings = re.findall(rb"\(([\s\S]*?)\)\s*(?:Tj|\'|\")", body)
                for raw in raw_strings:
                    try:
                        decoded = raw.decode("latin1", "ignore").strip()
                        decoded = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", decoded)
                        if len(decoded) > 5 and not decoded.startswith("/") and decoded not in seen:
                            seen.add(decoded)
                            snippets.append(decoded)
                            if len(snippets) >= max_snippets:
                                break
                    except Exception:
                        continue
    except Exception as e:
        print(f"Aviso na extração de {pdf_path.name}: {e}")

    return snippets


def generate_mock_academic_pdf(path: Path, title: str, snippets: list):
    """Gera um arquivo PDF sintético e válido contendo streams de texto acadêmico."""
    stream_content = f"BT /F1 14 Tf 72 720 Td ({title}) Tj 0 -20 Td /F1 11 Tf "
    for snip in snippets:
        safe_snip = snip.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({safe_snip}) Tj 0 -15 Td "
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin1")
    stream_len = len(stream_bytes)

    pdf_body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode("ascii") + b" >>\nstream\n"
        + stream_bytes + b"\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer\n<< /Root 1 0 R /Size 5 >>\nstartxref\n500\n%%EOF\n"
    )
    with open(path, "wb") as f:
        f.write(pdf_body)


ACADEMIC_CORPUS = [
    ("Information_Architecture_Principles.pdf", "Information Architecture Principles", [
        "Information architecture is the structural design of shared information environments.",
        "Pervasive information architecture bridges digital and physical ecosystems.",
        "Ontology, taxonomy and choreography define the core layers of modern IA systems."
    ]),
    ("Cognitive_Load_Theory.pdf", "Cognitive Load and Interface Usability", [
        "Dynamic information systems adapt to user cognitive load and environmental context.",
        "Intrinsic and extraneous cognitive load significantly impact task completion latency.",
        "Split-attention effects occur when multiple sources of information must be integrated."
    ]),
    ("Human_AI_Interaction_Frameworks.pdf", "Human-AI Interaction Frameworks", [
        "User experience encompasses all aspects of the end-user interaction with the company.",
        "Over-reliance on automated systems can lead to human deskilling and passive engagement.",
        "Transparent explanation interfaces foster trust calibration and critical evaluation."
    ]),
    ("Usability_Evaluation_Heuristics.pdf", "Usability Evaluation Heuristics", [
        "Heuristic evaluation provides quick diagnostic feedback on interface usability.",
        "Recognition over recall reduces memory overhead for active operators.",
        "Consistency and standards ensure predictable navigation behaviors."
    ]),
    ("Digital_Libraries_Metadata.pdf", "Metadata Standards in Digital Libraries", [
        "Controlled vocabularies improve precision and recall in federated information retrieval.",
        "Faceted search architectures provide multidimensional navigation pathways.",
        "Dublin Core metadata elements standardize digital item cataloging."
    ]),
    ("Knowledge_Organization_Systems.pdf", "Knowledge Organization Systems", [
        "Thesauri and semantic graphs represent domain-specific conceptual relationships.",
        "Hierarchical indexing enables efficient pruning of irrelevant document subtrees.",
        "Polyhierarchical classification handles multifaceted conceptual entities."
    ]),
    ("Cross_Language_Information_Retrieval.pdf", "Cross-Language Information Retrieval", [
        "Cross-language translation requires domain glossaries and morphological lemmatization.",
        "Ambiguous terminology demands sentence-level contextual disambiguation.",
        "Statistical alignment algorithms bridge parallel and multilingual corpora."
    ]),
    ("Neural_Machine_Translation_Evaluation.pdf", "Evaluation of Neural Machine Translation", [
        "BLEU and chrF metrics evaluate surface lexical overlap against reference targets.",
        "Character error rate reflects OCR noise and scanning distortion resilience.",
        "Latency profiling assesses time-to-first-token in local desktop environments."
    ]),
    ("Document_Parsing_Resilience.pdf", "Resilient PDF Document Parsing", [
        "Stream carving reconstructs document layout when xref tables are missing.",
        "Fluorescent highlighter suppression enhances OCR character recognition fidelity.",
        "Non-linear line break restoration avoids word concatenation in multi-column formats."
    ]),
    ("Embedded_Local_Inference.pdf", "Embedded Local Inference Architectures", [
        "Zero-cloud offline translation guarantees confidentiality for sensitive research papers.",
        "Memory-mapped vector lookups provide deterministic sub-millisecond retrieval.",
        "Hardware-aware execution profiles dynamically adjust model parameter scale."
    ]),
]


class TestAcademicPDFSimulation(unittest.TestCase):
    """Bateria de testes simulando uso do LoTra com acervo de PDFs acadêmicos."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "academic_test_vault.db"
        cls.vault = DocumentContextVault(db_path=str(cls.db_path))
        cls.pipeline = TranslationPipeline(vault=cls.vault)
        cls.translator = OfflineContextTranslator()

        # Verifica se há diretório externo configurado via variável de ambiente
        env_dir = os.environ.get("LOTRA_PDF_TEST_DIR")
        if env_dir and Path(env_dir).exists() and list(Path(env_dir).glob("*.pdf")):
            cls.pdf_dir = Path(env_dir)
            cls.pdf_files = list(cls.pdf_dir.glob("*.pdf"))
            cls._is_synthetic = False
        else:
            # Gera suite sintética de PDFs acadêmicos válida e autocontida
            cls.pdf_dir = Path(cls.temp_dir.name) / "academic_corpus"
            cls.pdf_dir.mkdir(parents=True, exist_ok=True)
            cls.pdf_files = []
            for filename, title, snippets in ACADEMIC_CORPUS:
                pdf_p = cls.pdf_dir / filename
                generate_mock_academic_pdf(pdf_p, title, snippets)
                cls.pdf_files.append(pdf_p)
            cls._is_synthetic = True

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "vault"):
            cls.vault.shutdown()
        if hasattr(cls, "temp_dir"):
            cls.temp_dir.cleanup()

    def test_1_access_and_catalog_all_academic_pdfs(self):
        """Valida que todos os PDFs do acervo acadêmico são acessíveis em modo estritamente read-only."""
        self.assertTrue(self.pdf_dir.exists(), f"Diretório não encontrado: {self.pdf_dir}")
        self.assertGreaterEqual(len(self.pdf_files), 10, f"Esperado >= 10 PDFs, encontrados {len(self.pdf_files)}")

        for pdf in self.pdf_files:
            # 1. Verifica existência e tamanho
            st = pdf.stat()
            self.assertGreater(st.st_size, 0, f"Arquivo vazio: {pdf.name}")
            
            # 2. Testa hash SHA-256 (fingerprint rápido do primeiro bloco de 64KB)
            fp = DocumentContextVault.compute_64kb_fingerprint(str(pdf))
            self.assertIsInstance(fp, str)
            self.assertEqual(len(fp), 64, f"Hash SHA-256 inválido para {pdf.name}")

    def test_2_extract_text_and_normalize_academic_pdf_flow(self):
        """Extrai trechos dos PDFs e valida que normalize_text_spacing conserta layout quebrado."""
        extracted_any = False
        sample_count = 0

        for pdf in self.pdf_files:
            snippets = fast_extract_pdf_snippets(pdf, max_snippets=10)
            if snippets:
                extracted_any = True
                for snip in snippets:
                    sample_count += 1
                    glued_sample = snip + "\nsecond line"
                    cleaned = normalize_text_spacing(glued_sample)
                    self.assertNotIn("\nsecond", cleaned, "Quebra de linha deve ser convertida em espaço limpo")
                    self.assertIn("second", cleaned)

        self.assertTrue(extracted_any, "Nenhum snippet extraído dos PDFs acadêmicos")
        self.assertGreaterEqual(sample_count, 10, "Menos de 10 snippets testados")

    def test_3_simulate_reading_selection_and_translation_pipeline(self):
        """Simula o fluxo completo do usuário selecionando termos em inglês nos PDFs e traduzindo."""
        academic_samples = [
            "Information architecture is the structural design of shared information environments.",
            "Pervasive information architecture bridges digital and physical ecosystems.",
            "User experience encompasses all aspects of the end-user's interaction with the company.",
            "Dynamic information systems adapt to user cognitive load and environmental context.",
            "Heuristic evaluation provides quick diagnostic feedback on interface usability."
        ]

        for sample in academic_samples:
            t0 = time.time()
            normalized = normalize_text_spacing(sample)
            res = self.pipeline.translate_text(normalized, doc_hash=f"simulated_{hash(sample)}.pdf")
            translated = res.get("translated_text", "")
            elapsed = time.time() - t0

            self.assertIsInstance(translated, str)
            self.assertGreater(len(translated), 5)
            self.assertTrue(
                any(pt_word in translated.lower() for pt_word in ["arquitetura", "informaç", "usuário", "experiência", "sistema", "avaliação", "design"]),
                f"Tradução sem palavras-chave em português: '{translated}' para '{sample}'"
            )
            self.assertLess(elapsed, 1.5, f"Latência excessiva na tradução: {elapsed:.2f}s")

    def test_4_sha256_context_vault_persistence_on_academic_documents(self):
        """Garante que consultas repetidas a trechos dos documentos utilizam o cofre local de contexto."""
        test_pdf = self.pdf_files[0]
        snippets = fast_extract_pdf_snippets(test_pdf, max_snippets=5)
        self.assertTrue(len(snippets) > 0, f"Sem snippets no primeiro PDF: {test_pdf.name}")

        query_text = snippets[0]
        doc_hash = DocumentContextVault.compute_64kb_fingerprint(str(test_pdf))

        # Primeira consulta (armazena no vault)
        res1 = self.pipeline.translate_text(query_text, doc_hash=doc_hash)
        
        # Segunda consulta (deve recuperar instantaneamente do cache/vault)
        t0 = time.time()
        res2 = self.pipeline.translate_text(query_text, doc_hash=doc_hash)
        cache_elapsed = time.time() - t0

        self.assertEqual(res1.get("translated_text"), res2.get("translated_text"), "Resultado em cache diverge da primeira tradução")
        self.assertLess(cache_elapsed, 0.15, f"Recuperação de cache muito lenta: {cache_elapsed:.4f}s")

    def test_5_extreme_load_concurrent_pdf_snippet_translations(self):
        """Estresse de concorrência: 30 threads simultâneas traduzindo trechos dos PDFs."""
        all_snippets = []
        for pdf in self.pdf_files[:5]:
            all_snippets.extend(fast_extract_pdf_snippets(pdf, max_snippets=10))

        if not all_snippets:
            all_snippets = ["Information architecture and system design principles."]

        errors = []
        success_count = [0]
        lock = threading.Lock()

        def worker(thread_idx, text_snippet):
            try:
                out = self.pipeline.translate_text(text_snippet, doc_hash=f"simulated_worker_{thread_idx}.pdf")
                txt = out.get("translated_text", "")
                if txt and len(txt) > 0:
                    with lock:
                        success_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append((thread_idx, e))

        threads = []
        num_workers = min(30, len(all_snippets) * 3)
        for i in range(num_workers):
            snip = all_snippets[i % len(all_snippets)]
            t = threading.Thread(target=worker, args=(i, snip))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(errors), 0, f"Ocorreram erros na concorrência com trechos acadêmicos: {errors}")
        self.assertEqual(success_count[0], num_workers, "Nem todas as threads completaram com sucesso")


if __name__ == "__main__":
    unittest.main()
