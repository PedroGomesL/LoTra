import sys
import os
import re
import time
import json
import urllib.request
from typing import List, Dict, Any, Tuple
from transformers import MarianMTModel, MarianTokenizer

ADVANCED_TESTS = [
    {
        "id": "TEST_1_GIRIAS_E_LINGUAGEM_COLOQUIAL",
        "title": "Gírias, Expressões Idiomáticas e Linguagem Coloquial",
        "source": "Man, out of nowhere the guy came to bullshit the hangout, dropped that fib on the crew and tried to act smart, but everyone saw that he was just trying to play dead because he was pissed off about the brush-off he got."
    },
    {
        "id": "TEST_2_SINTAXE_ENCAIXADA_LONGA",
        "title": "Oração Subordinada Encaixada / Sintaxe Longa Complexa",
        "source": "The report that the technical committee, whose members were appointed under intense political pressure last week, presented late last night to the lawmakers who defend the reform, although it was riddled with obvious methodological flaws, ended up being approved unanimously."
    },
    {
        "id": "TEST_3_PROVERBIOS_E_EXPRESSOES_MISTAS",
        "title": "Provérbios e Expressões Idiomáticas Mistas",
        "source": "The party was great, but since not everything is peaches and cream and in the land of the blind the one-eyed man is king, the boss showed up all of a sudden, wetted everyone's whistle and washed his hands before the roof caved in on him"
    },
    {
        "id": "TEST_4_VOCABULARIO_ROCOCO_E_LABIRINTICO",
        "title": "Vocabulário Rococó, Labiríntico e Múltiplos Provérbios",
        "source": "Although the erstwhile prelate—who, notwithstanding the bureaucratic kerfuffle that the regional synod kicked up during the preceding fiscal quarter, tried to high-hat the ecclesiastical vetting committee—surreptitiously proffered an unctuous exculpation reeking of high-falutin’ tomfoolery, the appellate panel, whose members (several of whom were sweating bullets over pending indictments) decided to play possum, ultimately ratified a slipshod rubric that, whilst tickling the fat cats upstairs, left the rank-and-file holding the bag, thereby proving that a bird in the hand is worth two in the bush when the chickens come home to roost."
    },
    {
        "id": "TEST_5_ANAFORAS_E_RASTREAMENTO_ENTIDADES",
        "title": "Resolução de Anáforas, Entidades Fictícias ('The former' vs 'The latter')",
        "source": "The parent corporation 'OmniCorp' notified its freshly acquired subsidiary 'TechZika'—whose flagship software 'Dadobras' triggered a massive legal debacle that it tried to sweep under the rug—that if the latter fails to restructure it entirely before the fatal deadline expires next Friday, the former will take draconian legal action against the majority shareholders who defended it, which will compel them to sue the latter for moral damages, thereby triggering a domino effect that forces the parent to offload it to third parties so they can sanitize it without the tax authorities realizing that it was the former that originally botched it."
    },
    {
        "id": "TEST_6_POLISSEMIA_EXTREMA_E_TROCADILHOS",
        "title": "Polissemia Extrema (Conductor, Concert, Baton, Battered)",
        "source": "The conductor's impromptu concert regarding the contentious concert-pitch reform couldn't be sanctioned because the erratic maestro remained entirely without concert control after losing the musical baton he used to direct the orchestra under the iron baton of the board, which subsequently battered the battered battered-cod vendor who happened to be conducting a parallel interview about the conduct of the conductor."
    }
]

def tokenize_clean(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r'[a-zA-ZÀ-ÿ0-9\-]+', text) if len(t) > 0]

# --- 1. Query LLM Local (Qwen 2.5 1.5B via Ollama GPU) ---
def query_llm_ollama(text: str, model: str = "qwen2.5:1.5b", ollama_url: str = "http://127.0.0.1:11434") -> Tuple[str, float, int, float]:
    system_instruction = (
        "Traduza o seguinte texto do inglês para o português brasileiro de forma natural, precisa e fluente, "
        "adaptando gírias, expressões idiomáticas e trocadilhos de maneira coerente em português. "
        "Retorne EXCLUSIVAMENTE a tradução final, sem introdução, sem notas e sem explicações adicionais."
    )
    prompt = f"{system_instruction}\n\nTexto: {text}"
    
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 1024
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=45.0) as resp:
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

# --- 2. Query MarianMT (Opus-MT Big en-pt) ---
class MarianMTRunner:
    def __init__(self, model_name: str = "Helsinki-NLP/opus-mt-tc-big-en-pt"):
        print(f"Carregando MarianMT ({model_name})...")
        t0 = time.perf_counter()
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name)
        print(f"MarianMT carregado em {time.perf_counter() - t0:.2f}s!")
        
    def translate(self, text: str) -> Tuple[str, float, int, float]:
        t0 = time.perf_counter()
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        gen = self.model.generate(
            **inputs, 
            max_length=512, 
            num_beams=4, 
            early_stopping=True
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        
        translated_text = self.tokenizer.decode(gen[0], skip_special_tokens=True).strip()
        tokens = tokenize_clean(translated_text)
        num_tokens = len(tokens)
        tps = (num_tokens / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0
        return translated_text, latency_ms, num_tokens, tps

def run_stress_benchmark():
    marian = MarianMTRunner()
    
    # Warmup
    print("Aquecendo modelos...")
    _ = query_llm_ollama("Test.", model="qwen2.5:1.5b")
    _ = marian.translate("Test.")
    print("Modelos aquecidos com sucesso!\n")
    
    results = []
    
    print("=" * 80)
    print("  SUPER-BENCHMARK LINGUÍSTICO: LLM (QWEN 2.5 1.5B) vs MARIANMT (OPUS-MT)")
    print("=" * 80)
    
    for item in ADVANCED_TESTS:
        t_id = item["id"]
        title = item["title"]
        src = item["source"]
        
        print("\n" + "=" * 78)
        print(f"  [{t_id}] - {title}")
        print("=" * 78)
        print(f"TEXTO ORIGINAL (EN):\n\"{src}\"\n")
        
        # 1. LLM
        llm_text, llm_lat, llm_tok, llm_tps = query_llm_ollama(src, model="qwen2.5:1.5b")
        print(f"--- QWEN 2.5 1.5B (LLM na GPU Vulkan) ---")
        print(f"Tempo: {llm_lat:.1f} ms | Tokens: {llm_tok} | Throughput: {llm_tps:.1f} tok/s")
        print(f"Tradução:\n\"{llm_text}\"\n")
        
        # 2. MarianMT
        marian_text, marian_lat, marian_tok, marian_tps = marian.translate(src)
        print(f"--- MARIANMT (Opus-MT NMT na CPU) ---")
        print(f"Tempo: {marian_lat:.1f} ms | Tokens: {marian_tok} | Throughput: {marian_tps:.1f} tok/s")
        print(f"Tradução:\n\"{marian_text}\"\n")
        
        speedup = (llm_lat / marian_lat) if marian_lat > 0 else 1.0
        
        results.append({
            "test_id": t_id,
            "title": title,
            "source_en": src,
            "llm": {
                "model": "qwen2.5:1.5b",
                "latency_ms": round(llm_lat, 2),
                "throughput_tps": round(llm_tps, 2),
                "tokens": llm_tok,
                "translation": llm_text
            },
            "marian": {
                "model": "Helsinki-NLP/opus-mt-tc-big-en-pt",
                "latency_ms": round(marian_lat, 2),
                "throughput_tps": round(marian_tps, 2),
                "tokens": marian_tok,
                "translation": marian_text
            },
            "speedup_ratio": round(speedup, 2)
        })
        
    out_file = "advanced_stress_benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\n>> Resultados completos salvos em: {out_file}")

if __name__ == "__main__":
    run_stress_benchmark()
