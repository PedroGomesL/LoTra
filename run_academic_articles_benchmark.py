import sys
import os
import re
import time
import json
import urllib.request
from typing import List, Dict, Any, Tuple
from transformers import MarianMTModel, MarianTokenizer

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ACADEMIC_TESTS = [
    {
        "id": "ARTICLE_1_DEVILS_ADVOCATE_ABSTRACT",
        "title": "Artigo 1: Abstract - Devil's Advocate em Tomada de Decisão com LLM",
        "source": "Group decision making plays a crucial role in our complex andinterconnected world. The rise of AI technologies has the potentialto provide data-driven insights to facilitate group decision making,although it is found that groups do not always utilize AI assistanceappropriately. In this paper, we aim to examine whether and howthe introduction of a devil’s advocate in the AI-assisted group deci-sion making processes could help groups better utilize AI assistanceand change the perceptions of group processes during decisionmaking. Inspired by the exceptional conversational capabilities ex-hibited by modern large language models (LLMs), we design fourdifferent styles of devil’s advocate powered by LLMs, varying theirinteractivity (i.e., interactive vs. non-interactive) and their target ofobjection (i.e., challenge the AI recommendation or the majorityopinion within the group). Through a randomized human-subjectexperiment, we find evidence suggesting that LLM-powered devil’sadvocates that argue against the AI model’s decision recommenda-tion have the potential to promote groups’ appropriate reliance onAI. Meanwhile, the introduction of LLM-powered devil’s advocateusually does not lead to substantial increases in people’s perceivedworkload for completing the group decision making tasks, whileinteractive LLM-powered devil’s advocates are perceived as morecollaborating and of higher quality. We conclude by discussing thepractical implications of our findings."
    },
    {
        "id": "ARTICLE_2_GROUPTHINK_CITATIONS",
        "title": "Artigo 2: Discussões em Grupo, Groupthink e Citações Bibliográficas ACM",
        "source": "Group discussions are paramount for fostering productive collab-oration in group decision making [ 96, 100]. An ideal group dis-cussion process could facilitate knowledge sharing [29 ], opinionexchange [77 ], and hence generate converged and well-informedcollaborative decisions. However, the quality of group discussions isinfluenced by various factors. For instance, Curşeu et al. [20 ] foundthat gender diversity and the group-level need for cognition affectgroup discussion quality, which in turn predicts group performance.They also found that group members may not always be active inexchanging information with others during group discussions. Infact, the lack of opposing perspectives during group discussionsmay easily lead groups to the “groupthink” status [ 42 ], i.e., a groupof people quickly converge to a consensus as group members desirefor conformity within the group, which often results in poor deci-sions [ 2, 14 , 19 , 41 ]. Therefore, a large body of previous researchhas pointed out the importance of encouraging divergent opin-ions in collaborative interactions [ 36 , 94 ], as discussions aroundthese disagreements have the potential to bring about a deeper andmore comprehensive understanding of the topic [ 86 ]."
    },
    {
        "id": "ARTICLE_3_HIGHER_ORDER_THINKING_HCI",
        "title": "Artigo 3: Higher-Order Thinking Skills e Comunidade HCI",
        "source": "Higher-order thinking skills in general have received little attention from the HCI community to date, though some scholars from other research fields have examined the use of technology to foster higher-order thinking skills [61]. That being said, there exists a long history of scholarship on the ways that technology can be harnessed to promote critical thinking, creative thinking, and support educational goals in general. Early research included discussions about the roles of computers in schools [118], and proposals, such as Jonassen’s concept of Mindtools [68]. HCIresearchers have long been interested in creativity support tools [48], and have developed numerous methods for evaluating their impacts on creative thinking [113]. Recent research in HCI and related fields has also explored various techniques for promoting critical thinking in a variety of application domains, including websearch [146],online collaboration[126], educational exhibitions [81], online learning [63], digital media literacy [108], data sensing [80], engineering research [6], and misinformation mitigation [14, 37]. With the power and flexibility of AI, extraheric AI has the potential to accelerate this research direction and play a substantial role in the development and promotionof higher-order thinking skills."
    },
    {
        "id": "ARTICLE_4_SHNEIDERMAN_FRAMEWORK",
        "title": "Artigo 4: Taxonomia de Ben Shneiderman (Orthotics, Prosthetics, Exoskeletons)",
        "source": "Human-AI interaction systems are typically designed to directly support human tasks, such as by taking on subtasks, accelerating processes, or reducing input effort. In his book Human-Centered AI, Ben Schneiderman offers the following categorization for tools serving human needs [124]:\n• Orthotics: Systems that enhance performance in specific tasks (e.g., auto-completion, FlashFill in Excel, and Copilot for coding).\n• Prosthetics: Systems that replace missing capabilities (e.g., real-time captioning, and visual information verbalization).\n• Exoskeletons: Systems that expand human capacities related to specific tasks (e.g., language translation, and information search assistants).\nMany existing human-AI interaction systems fit one or more of these categories, although their classification can vary depending on context and user capabilities. For example, a language translation application serves as prosthetics for users with no background in a language, but acts as exoskeleton for those with some proficiency."
    }
]

def tokenize_clean(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r'[a-zA-ZÀ-ÿ0-9\-]+', text) if len(t) > 0]

# --- 1. Query LLM Local (Qwen 2.5 1.5B via Ollama GPU) ---
def query_llm_ollama(text: str, model: str = "qwen2.5:1.5b", ollama_url: str = "http://127.0.0.1:11434") -> Tuple[str, float, int, float]:
    system_instruction = (
        "Traduza o seguinte trecho de artigo acadêmico/científico do inglês para o português brasileiro de forma formal, "
        "precisa e elegante. Mantenha os termos técnicos adequados da computação/IA e preserve citações bibliográficas numéricas como [96, 100]. "
        "Retorne EXCLUSIVAMENTE a tradução final, sem introdução, sem notas de rodapé e sem explicações."
    )
    prompt = f"{system_instruction}\n\nTexto:\n{text}"
    
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
    with urllib.request.urlopen(req, timeout=60.0) as resp:
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
        
        # MarianMT é treinado no nível de sentenças. Segmentamos por quebras de linha e sentenças
        raw_lines = [l.strip() for l in text.split("\n") if l.strip()]
        translated_lines = []
        
        for line in raw_lines:
            # Divide sentenças por pontuação final, preservando o fluxo
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', line) if s.strip()]
            line_parts = []
            for sent in sentences:
                inputs = self.tokenizer(sent, return_tensors="pt", padding=True, truncation=True, max_length=512)
                gen = self.model.generate(
                    **inputs, 
                    max_length=512, 
                    num_beams=4, 
                    early_stopping=True
                )
                line_parts.append(self.tokenizer.decode(gen[0], skip_special_tokens=True).strip())
            translated_lines.append(" ".join(line_parts))
            
        latency_ms = (time.perf_counter() - t0) * 1000.0
        final_trans = "\n".join(translated_lines)
        tokens = tokenize_clean(final_trans)
        num_tokens = len(tokens)
        tps = (num_tokens / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0
        return final_trans, latency_ms, num_tokens, tps

def run_academic_benchmark():
    marian = MarianMTRunner()
    
    print("Aquecendo modelos...")
    _ = query_llm_ollama("Abstract warmup.", model="qwen2.5:1.5b")
    _ = marian.translate("Abstract warmup.")
    print("Modelos aquecidos com sucesso!\n")
    
    results = []
    
    print("=" * 80)
    print("  BENCHMARK EM ARTIGOS CIENTÍFICOS: LLM (QWEN 2.5 1.5B) vs MARIANMT (OPUS-MT)")
    print("=" * 80)
    
    for item in ACADEMIC_TESTS:
        t_id = item["id"]
        title = item["title"]
        src = item["source"]
        
        print("\n" + "=" * 78)
        print(f"  [{t_id}] - {title}")
        print("=" * 78)
        
        # 1. LLM
        llm_text, llm_lat, llm_tok, llm_tps = query_llm_ollama(src, model="qwen2.5:1.5b")
        print(f"\n--- QWEN 2.5 1.5B (LLM na GPU Vulkan) ---")
        print(f"Tempo: {llm_lat:.1f} ms | Tokens: {llm_tok} | Throughput: {llm_tps:.1f} tok/s")
        print(f"Tradução:\n{llm_text}\n")
        
        # 2. MarianMT
        marian_text, marian_lat, marian_tok, marian_tps = marian.translate(src)
        print(f"--- MARIANMT (Opus-MT NMT na CPU) ---")
        print(f"Tempo: {marian_lat:.1f} ms | Tokens: {marian_tok} | Throughput: {marian_tps:.1f} tok/s")
        print(f"Tradução:\n{marian_text}\n")
        
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
        
    out_file = "academic_articles_benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\n>> Resultados completos salvos em: {out_file}")

if __name__ == "__main__":
    run_academic_benchmark()
