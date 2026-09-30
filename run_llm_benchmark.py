import sys
import os
import re
import time
import json
import math
from collections import Counter
from typing import List, Dict, Any, Tuple

sys.path.insert(0, os.path.abspath("src"))
from translation_engine import TranslationPipeline

# Standard BLEU calculation (Papineni et al., 2002)
def get_ngrams(tokens: List[str], n: int) -> Counter:
    return Counter([tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)])

def compute_bleu(candidate_tokens: List[str], reference_tokens: List[str], max_n: int = 4) -> Dict[str, float]:
    cand_len = len(candidate_tokens)
    ref_len = len(reference_tokens)
    
    if cand_len == 0:
        return {"bleu": 0.0, "p1": 0.0, "p2": 0.0, "p3": 0.0, "p4": 0.0, "bp": 0.0}
        
    precisions = []
    for n in range(1, max_n + 1):
        cand_ngrams = get_ngrams(candidate_tokens, n)
        ref_ngrams = get_ngrams(reference_tokens, n)
        
        clipped_count = 0
        total_cand_ngrams = sum(cand_ngrams.values())
        
        for ngram, count in cand_ngrams.items():
            clipped_count += min(count, ref_ngrams.get(ngram, 0))
            
        if total_cand_ngrams > 0 and clipped_count > 0:
            precisions.append(clipped_count / total_cand_ngrams)
        else:
            precisions.append(0.0)
            
    # Brevity Penalty
    if cand_len > ref_len:
        bp = 1.0
    else:
        bp = math.exp(1.0 - (ref_len / cand_len)) if cand_len > 0 else 0.0
        
    # Geometric mean of precisions (add epsilon for 0 counts)
    p_log_sum = 0.0
    valid_p = True
    for p in precisions:
        if p > 0:
            p_log_sum += math.log(p)
        else:
            valid_p = False
            break
            
    if valid_p:
        bleu = bp * math.exp(p_log_sum / max_n)
    else:
        # Smooth BLEU if higher n-grams are zero
        smoothed_sum = sum(math.log(p) if p > 0 else math.log(1e-4) for p in precisions)
        bleu = bp * math.exp(smoothed_sum / max_n)
        
    return {
        "bleu": round(bleu * 100.0, 2),
        "p1": round(precisions[0] * 100.0, 2) if len(precisions) > 0 else 0.0,
        "p2": round(precisions[1] * 100.0, 2) if len(precisions) > 1 else 0.0,
        "p3": round(precisions[2] * 100.0, 2) if len(precisions) > 2 else 0.0,
        "p4": round(precisions[3] * 100.0, 2) if len(precisions) > 3 else 0.0,
        "bp": round(bp, 4)
    }

def tokenize_clean(text: str) -> List[str]:
    # Tokenize preserving Portuguese accents and lowercasing
    return [t.lower() for t in re.findall(r'[a-zA-ZÀ-ÿ0-9\-]+', text) if len(t) > 0]

TEST_DATA = [
    {
        "id": "TEST_1_DIREITO_CONSTITUCIONAL",
        "domain": "Direito Constitucional & Teoria do Estado",
        "source": "The principle of the separation of powers, enshrined by Montesquieu, operates as a system of checks and balances designed to prevent state arbitrariness and safeguard fundamental rights. Constitutional mutation, in turn, evidences the plasticity of the normative text in the face of the factual demands of social mutability, formally distinguishing itself from amendment, which requires the rigid derived legislative iter.",
        "reference": "O princípio da separação dos poderes, consagrado por Montesquieu, opera como um sistema de freios e contrapesos projetado para evitar o arbítrio estatal e salvaguardar os direitos fundamentais. A mutação constitucional, por sua vez, evidencia a plasticidade do texto normativo diante das demandas fáticas da mutabilidade social, distinguindo-se formalmente da reforma, que exige o rígido iter legislativo derivado."
    },
    {
        "id": "TEST_2_ASTROFISICA_NUCLEAR",
        "domain": "Astrofísica & Cosmologia",
        "source": "Primordial nucleosynthesis occurred within the first few minutes after the Big Bang, synthesizing hydrogen and helium nuclei and traces of lithium. However, the observed abundance of heavy elements in the interstellar medium depends primarily on stellar nucleosynthesis in type II supernovae and the chemical enrichment driven by stellar winds from Wolf-Rayet stars.",
        "reference": "A nucleossíntese primordial ocorreu nos primeiros minutos após o Big Bang, sintetizando núcleos de hidrogênio e hélio e traços de lítio. No entanto, a abundância observada de elementos pesados no meio interestelar depende primariamente da nucleossíntese estelar em supernovas do tipo II e do enriquecimento químico impulsionado pelos ventos estelares de estrelas Wolf-Rayet."
    },
    {
        "id": "TEST_3_BIOLOGIA_MOLECULAR",
        "domain": "Biologia Molecular & Epigenética",
        "source": "Epigenetic regulation of gene expression involves post-translational modifications of histones, such as methylation and acetylation, as well as DNA methylation at CpG islands. These mechanisms modulate chromatin accessibility to RNA polymerase II, altering the cellular phenotype without modifying the underlying nucleotide sequence of the genome.",
        "reference": "A regulação epigenética da expressão gênica envolve modificações pós-traducionais de histonas, tais como metilação e acetilação, bem como metilação do DNA em ilhas CpG. Esses mecanismos modulam a acessibilidade da cromatina à RNA polimerase II, alterando o fenótipo celular sem modificar a sequência subjacente de nucleotídeos do genoma."
    },
    {
        "id": "TEST_4_TEORIA_LITERARIA",
        "domain": "Teoria Literária & Filosofia da Linguagem",
        "source": "Mikhail Bakhtin's concept of polyphony breaks with the monology of the traditional novel, granting the characters' voices an ontological autonomy relative to the author's consciousness. The chronotope, in turn, functions as the space-time intersection category that structures narrative architectonics, allowing for the aesthetic realization of historical becoming in the work of art.",
        "reference": "O conceito de polifonia de Mikhail Bakhtin rompe com a monologia do romance tradicional, concedendo às vozes das personagens uma autonomia ontológica em relação à consciência do autor. O cronotopo, por sua vez, funciona como a categoria de intersecção espaço-temporal que estrutura a arquitetônica narrativa, permitindo a realização estética do devir histórico na obra de arte."
    },
    {
        "id": "TEST_5_MACROECONOMIA",
        "domain": "Macroeconomia & Teoria Monetária",
        "source": "The expectations-augmented Phillips curve postulates that there is no permanent trade-off between inflation and unemployment in the long run. Consequently, unanticipated expansionary monetary policies generate only nominal effects on aggregate output, resulting in the neutrality of money when economic agents perfectly adjust their inflationary projections.",
        "reference": "A curva de Phillips aumentada pelas expectativas postula que não há trade-off permanente entre inflação e desemprego no longo prazo. Consequentemente, políticas monetárias expansionistas não antecipadas geram apenas efeitos nominais sobre o produto agregado, resultando na neutralidade da moeda quando os agentes econômicos ajustam perfeitamente suas projeções inflacionárias."
    }
]

# Set of words considered legitimate international scientific/proper terms or latinisms
LEGITIMATE_FOREIGN_TERMS = {
    "big", "bang", "wolf-rayet", "cpg", "rna", "ii", "montesquieu", 
    "bakhtin", "mikhail", "phillips", "dna", "trade-off", "iter"
}

def analyze_untranslated_words(source_text: str, trans_text: str) -> Tuple[int, List[str], float]:
    src_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', source_text)]
    trans_lower = trans_text.lower()
    
    # Portuguese common words that share spelling with English words
    pt_overlap = {"para", "como", "com", "dos", "das", "que", "uma", "este", "esta", "por"}
    
    untranslated = []
    for w in set(src_words):
        if w in pt_overlap:
            continue
        # Check if the exact english word is present in translated output
        if re.search(rf'\b{re.escape(w)}\b', trans_lower):
            untranslated.append(w)
            
    # Classify which are legitimate technical proper nouns vs untranslated text
    foreign_technical = [w for w in untranslated if w in LEGITIMATE_FOREIGN_TERMS]
    actual_untranslated = [w for w in untranslated if w not in LEGITIMATE_FOREIGN_TERMS]
    
    accuracy_rate = ((len(set(src_words)) - len(actual_untranslated)) / len(set(src_words))) * 100.0
    return len(actual_untranslated), actual_untranslated, foreign_technical, round(accuracy_rate, 2)

def run_benchmark():
    pipeline = TranslationPipeline()
    results = []

    print("=" * 75)
    print("  LOTRA BENCHMARK COM LLM LOCAL (Qwen 2.5 3B no AMD Radeon Graphics GPU)")
    print("=" * 75)

    for item in TEST_DATA:
        test_id = item["id"]
        domain = item["domain"]
        source = item["source"]
        ref = item["reference"]
        
        print(f"\n>>> Executando {test_id} ({domain})...")
        
        # Fresh unique hash to ensure we benchmark the live neural inference (bypassing cached results)
        doc_hash = f"bench_live_{test_id}_{int(time.time() * 1000)}"
        
        t_start = time.perf_counter()
        res = pipeline.translate_text(source, doc_hash=doc_hash)
        t_total_ms = (time.perf_counter() - t_start) * 1000.0
        
        translated = res["translated_text"]
        engine = res.get("engine_used", "Unknown")
        model = res.get("model_name", "Unknown")
        reported_latency = res.get("latency_ms", t_total_ms)
        
        # Token metrics
        cand_tokens = tokenize_clean(translated)
        ref_tokens = tokenize_clean(ref)
        src_tokens = tokenize_clean(source)
        
        # Calculate BLEU
        bleu_metrics = compute_bleu(cand_tokens, ref_tokens)
        
        # Analyze untranslated words
        untrans_count, untrans_words, foreign_tech, accuracy = analyze_untranslated_words(source, translated)
        
        # Token throughput
        num_generated_tokens = len(cand_tokens)
        tok_per_sec = (num_generated_tokens / (reported_latency / 1000.0)) if reported_latency > 0 else 0.0
        
        print(f"  * Motor Utilizado     : {engine}")
        print(f"  * Modelo              : {model}")
        print(f"  * Latência Total      : {reported_latency:.2f} ms")
        print(f"  * Tokens Gerados      : {num_generated_tokens} tokens (~{tok_per_sec:.1f} tok/s)")
        print(f"  * BLEU-4 Score        : {bleu_metrics['bleu']} (P1={bleu_metrics['p1']}%, P2={bleu_metrics['p2']}%, BP={bleu_metrics['bp']})")
        print(f"  * Taxa de Acerto      : {accuracy}%")
        print(f"  * Palavras em Inglês  : {untrans_count} residuais (Residuais: {untrans_words} | Termos Técnicos Próprios: {foreign_tech})")
        print(f"\n  [Tradução Gerada]:")
        print(f"  \"{translated}\"")
        
        results.append({
            "test_id": test_id,
            "domain": domain,
            "source_tokens": len(src_tokens),
            "generated_tokens": num_generated_tokens,
            "latency_ms": round(reported_latency, 2),
            "tokens_per_sec": round(tok_per_sec, 2),
            "engine": engine,
            "model": model,
            "bleu": bleu_metrics,
            "accuracy_pct": accuracy,
            "untranslated_count": untrans_count,
            "untranslated_words": untrans_words,
            "foreign_technical_terms": foreign_tech,
            "translated_text": translated,
            "reference_text": ref
        })

    # Save complete benchmark process to JSON
    output_file = "benchmark_results_llm.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print("\n" + "=" * 75)
    print(f"  BENCHMARK FINALIZADO! Dados salvos em: {output_file}")
    print("=" * 75)

if __name__ == "__main__":
    run_benchmark()
