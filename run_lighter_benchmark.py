import sys
import os
import re
import time
import json
import math
import urllib.request
from collections import Counter
from typing import List, Dict, Any, Tuple

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
        
    # Geometric mean of precisions
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

LEGITIMATE_FOREIGN_TERMS = {
    "big", "bang", "wolf-rayet", "cpg", "rna", "ii", "montesquieu", 
    "bakhtin", "mikhail", "phillips", "dna", "trade-off", "iter"
}

def analyze_untranslated_words(source_text: str, trans_text: str) -> Tuple[int, List[str], List[str], float]:
    src_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', source_text)]
    trans_lower = trans_text.lower()
    
    pt_overlap = {"para", "como", "com", "dos", "das", "que", "uma", "este", "esta", "por"}
    
    untranslated = []
    for w in set(src_words):
        if w in pt_overlap:
            continue
        if re.search(rf'\b{re.escape(w)}\b', trans_lower):
            untranslated.append(w)
            
    foreign_technical = [w for w in untranslated if w in LEGITIMATE_FOREIGN_TERMS]
    actual_untranslated = [w for w in untranslated if w not in LEGITIMATE_FOREIGN_TERMS]
    
    accuracy_rate = ((len(set(src_words)) - len(actual_untranslated)) / len(set(src_words))) * 100.0
    return len(actual_untranslated), actual_untranslated, foreign_technical, round(accuracy_rate, 2)

def query_ollama(model: str, text: str, ollama_url: str = "http://127.0.0.1:11434") -> Tuple[str, float, int, float]:
    # We test via the standard instruction prompt
    system_instruction = (
        "Traduza o seguinte texto do inglês para o português brasileiro de forma natural, precisa e fluente. "
        "Retorne EXCLUSIVAMENTE a tradução final, sem introdução, sem aspas adicionais e sem explicações."
    )
    prompt = f"{system_instruction}\n\nTexto: {text}"
    
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 512
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    latency_ms = (time.perf_counter() - t0) * 1000.0
    
    raw_res = data.get("response", "").strip()
    if (raw_res.startswith('"') and raw_res.endswith('"')) or (raw_res.startswith("“") and raw_res.endswith("”")):
        raw_res = raw_res[1:-1].strip()
    if raw_res.lower().startswith("tradução:"):
        raw_res = raw_res[len("tradução:"):].strip()
    if raw_res.lower().startswith("tradução :"):
        raw_res = raw_res[len("tradução :"):].strip()
        
    eval_count = data.get("eval_count", len(tokenize_clean(raw_res)))
    eval_duration_ns = data.get("eval_duration", 0)
    
    if eval_duration_ns > 0:
        tps = (eval_count / (eval_duration_ns / 1e9))
    else:
        tps = (len(tokenize_clean(raw_res)) / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0

    return raw_res, latency_ms, eval_count, tps

def run_tests():
    models_to_test = ["qwen2.5:1.5b", "qwen2.5:0.5b"]
    all_results = {}
    
    for model in models_to_test:
        print(f"\n=======================================================")
        print(f"  TESTANDO MODELO: {model} (GPU AMD Radeon Vulkan)")
        print(f"=======================================================")
        model_results = []
        
        for item in TEST_DATA:
            test_id = item["id"]
            domain = item["domain"]
            source = item["source"]
            ref = item["reference"]
            
            print(f"\n>>> [{model}] Executando {test_id} ({domain})...")
            
            translated, latency_ms, eval_tokens, tps = query_ollama(model, source)
            
            cand_tokens = tokenize_clean(translated)
            ref_tokens = tokenize_clean(ref)
            
            bleu = compute_bleu(cand_tokens, ref_tokens)
            untrans_count, untrans_words, foreign_tech, accuracy = analyze_untranslated_words(source, translated)
            
            print(f"  * Latência Total     : {latency_ms:.2f} ms")
            print(f"  * Tokens Gerados     : {len(cand_tokens)} tokens (~{tps:.1f} tok/s)")
            print(f"  * BLEU-4 Score       : {bleu['bleu']} (P1={bleu['p1']}%, P2={bleu['p2']}%, BP={bleu['bp']})")
            print(f"  * Taxa de Acerto     : {accuracy}%")
            print(f"  * Palavras em Inglês : {untrans_count} residuais {untrans_words}")
            print(f"  * Tradução           : \"{translated}\"")
            
            model_results.append({
                "test_id": test_id,
                "domain": domain,
                "latency_ms": round(latency_ms, 2),
                "tokens_per_sec": round(tps, 2),
                "generated_tokens": len(cand_tokens),
                "bleu": bleu,
                "accuracy_pct": accuracy,
                "untranslated_count": untrans_count,
                "untranslated_words": untrans_words,
                "foreign_technical_terms": foreign_tech,
                "translated_text": translated,
                "reference_text": ref
            })
            
        all_results[model] = model_results
        
    out_file = "benchmark_results_lighter_models.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
        
    print(f"\nResultados gravados em {out_file}")

if __name__ == "__main__":
    run_tests()
