"""
Executa o benchmark de OCR sobre todo o dataset de teste (páginas digitais vs escaneadas)
incluindo palavras isoladas, idioms, parágrafos e página A4 complexa com diagramas embutidos,
usando o Windows Media OCR nativo, registrando métricas exatas de tempo e taxa de acerto.
"""
import os
import json
import time
import re
import subprocess
from accuracy_metrics import compute_cer, compute_wer, compute_accuracy

BASE_DIR = os.path.dirname(__file__)
DATASET_PATH = os.path.join(BASE_DIR, "dataset.json")
A4_GT_PATH = os.path.join(BASE_DIR, "a4_ground_truth.json")
IMAGES_DIR = os.path.join(BASE_DIR, "test_images")
PS_SCRIPT = os.path.join(BASE_DIR, "win_ocr.ps1")

with open(DATASET_PATH, "r", encoding="utf-8") as f:
    DATASET = json.load(f)

A4_GT = {}
if os.path.exists(A4_GT_PATH):
    with open(A4_GT_PATH, "r", encoding="utf-8") as f:
        A4_GT = json.load(f)

def run_win_ocr(image_path):
    abs_path = os.path.abspath(image_path)
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", PS_SCRIPT,
        "-ImagePath", abs_path
    ]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    t1 = time.perf_counter()
    
    stdout = res.stdout.strip()
    # Limpa caracteres de controle ASCII residuais
    clean_stdout = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', stdout)
    try:
        data = json.loads(clean_stdout, strict=False)
        return {
            "extracted_text": data.get("Text", ""),
            "inference_ms": float(data.get("InferenceMs", 0.0)),
            "pipeline_ms": float(data.get("ElapsedMs", 0.0)),
            "subproc_elapsed_ms": (t1 - t0) * 1000.0,
            "success": data.get("Success", False)
        }
    except Exception:
        # Fallback se houver algum erro de deserialização
        start_idx = stdout.find('{')
        end_idx = stdout.rfind('}')
        if start_idx != -1 and end_idx != -1:
            try:
                sub = stdout[start_idx:end_idx+1]
                data = json.loads(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', sub), strict=False)
                return {
                    "extracted_text": data.get("Text", ""),
                    "inference_ms": float(data.get("InferenceMs", 0.0)),
                    "pipeline_ms": float(data.get("ElapsedMs", 0.0)),
                    "subproc_elapsed_ms": (t1 - t0) * 1000.0,
                    "success": data.get("Success", False)
                }
            except Exception:
                pass
        return {
            "extracted_text": stdout,
            "inference_ms": 0.0,
            "pipeline_ms": (t1 - t0) * 1000.0,
            "subproc_elapsed_ms": (t1 - t0) * 1000.0,
            "success": bool(stdout)
        }

def run_benchmark():
    results = []
    
    # 1. Palavras e Expressões
    test_cases = []
    for item in DATASET["single_words"] + DATASET["idioms_and_phrasal_verbs"]:
        test_cases.append({
            "id": item["id"],
            "type": "word/idiom",
            "ground_truth": item["context"],
            "target_term": item["text"]
        })
        
    # 2. Parágrafos de livros
    paragraph_targets = {
        "p1": "Winston Smith",
        "p2": "backpropagation"
    }
    for item in DATASET["book_paragraphs"]:
        test_cases.append({
            "id": item["id"],
            "type": "paragraph",
            "ground_truth": item["text"],
            "target_term": paragraph_targets.get(item["id"], "networks")
        })
        
    # 3. Página A4 Complexa com Diagramas Embutidos
    a4_full_text = " ".join([
        A4_GT.get("doc_metadata", {}).get("title", ""),
        A4_GT.get("abstract", ""),
        A4_GT.get("column_1_text", ""),
        " ".join(A4_GT.get("diagram_internal_texts", [])),
        A4_GT.get("column_2_text", ""),
        A4_GT.get("figure_caption", "")
    ]).strip()
    
    diagram_boxes = [
        "Room Temp",
        "4K Stage",
        "Still Stage",
        "Cold Plate",
        "Mixing Chamber",
        "Dispersive Readout"
    ]
    
    test_cases.append({
        "id": "a4_complex_page",
        "type": "complex_a4_mixed_diagram",
        "ground_truth": a4_full_text if a4_full_text else DATASET.get("complex_a4_page", {}).get("body_text", ""),
        "target_term": "Cryogenic Microwave Routing",
        "diagram_texts": diagram_boxes
    })
        
    print("=" * 80)
    print("INICIANDO BENCHMARK DE OCR: DIGITAL (DIRETO) VS ESCANEADO (OCR RUÍDO)")
    print("=" * 80)
    
    for case in test_cases:
        cid = case["id"]
        gt = case["ground_truth"]
        
        # Teste 1: Digital Limpo
        dig_img = os.path.join(IMAGES_DIR, f"{cid}_digital.png")
        if not os.path.exists(dig_img):
            print(f"[AVISO] Imagem {dig_img} não encontrada. Pulando...")
            continue
            
        dig_ocr = run_win_ocr(dig_img)
        dig_clean = dig_ocr["extracted_text"]
        for prefix in ["Book Vocabulary Entry", "Excerpt from 1984 (George Orwell)", "Technical / Scientific Reading Excerpt"]:
            if dig_clean.startswith(prefix):
                dig_clean = dig_clean[len(prefix):].strip()
                
        dig_cer = compute_cer(gt, dig_clean)
        dig_wer = compute_wer(gt, dig_clean)
        dig_acc = compute_accuracy(gt, dig_clean)
        dig_found = case["target_term"].lower() in dig_ocr["extracted_text"].lower()
        
        # Teste 2: Escaneado
        scan_img = os.path.join(IMAGES_DIR, f"{cid}_scanned.png")
        scan_ocr = run_win_ocr(scan_img)
        scan_clean = scan_ocr["extracted_text"]
        for prefix in ["Book Vocabulary Entry", "Excerpt from 1984 (George Orwell)", "Technical / Scientific Reading Excerpt"]:
            if scan_clean.startswith(prefix):
                scan_clean = scan_clean[len(prefix):].strip()
                
        scan_cer = compute_cer(gt, scan_clean)
        scan_wer = compute_wer(gt, scan_clean)
        scan_acc = compute_accuracy(gt, scan_clean)
        scan_found = case["target_term"].lower() in scan_ocr["extracted_text"].lower()
        
        # Se for página A4, checa detecção de diagramas internos
        diagram_analysis = None
        if "diagram_texts" in case and case["diagram_texts"]:
            dig_diag_found = sum(1 for dt in case["diagram_texts"] if dt.lower() in dig_ocr["extracted_text"].lower())
            scan_diag_found = sum(1 for dt in case["diagram_texts"] if dt.lower() in scan_ocr["extracted_text"].lower())
            diagram_analysis = {
                "total_diagram_texts": len(case["diagram_texts"]),
                "digital_detected_count": dig_diag_found,
                "scanned_detected_count": scan_diag_found,
                "digital_diagram_acc_pct": round((dig_diag_found / len(case["diagram_texts"])) * 100.0, 1),
                "scanned_diagram_acc_pct": round((scan_diag_found / len(case["diagram_texts"])) * 100.0, 1)
            }
        
        res = {
            "id": cid,
            "type": case["type"],
            "ground_truth": gt,
            "target_term": case["target_term"],
            "digital": {
                "extracted": dig_clean,
                "inference_ms": dig_ocr["inference_ms"],
                "pipeline_ms": dig_ocr["pipeline_ms"],
                "cer": dig_cer,
                "wer": dig_wer,
                "accuracy_pct": dig_acc,
                "target_found": dig_found
            },
            "scanned": {
                "extracted": scan_clean,
                "inference_ms": scan_ocr["inference_ms"],
                "pipeline_ms": scan_ocr["pipeline_ms"],
                "cer": scan_cer,
                "wer": scan_wer,
                "accuracy_pct": scan_acc,
                "target_found": scan_found
            }
        }
        if diagram_analysis:
            res["diagram_analysis"] = diagram_analysis
            
        results.append(res)
        
        print(f"[{cid.upper()}] {case['type']} | Digital: {dig_ocr['inference_ms']:.1f}ms (Acc: {dig_acc:.1f}%) | Escaneado: {scan_ocr['inference_ms']:.1f}ms (Acc: {scan_acc:.1f}%)")
        if diagram_analysis:
            print(f"  -> Diagramas Detectados: Digital {diagram_analysis['digital_detected_count']}/{diagram_analysis['total_diagram_texts']} | Escaneado {diagram_analysis['scanned_detected_count']}/{diagram_analysis['total_diagram_texts']}")
        
    out_file = os.path.join(BASE_DIR, "ocr_benchmark_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print(f"\n[SUCESSO] Resultados consolidados salvos em: {out_file}")

if __name__ == "__main__":
    run_benchmark()
