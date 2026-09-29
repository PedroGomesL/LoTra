"""
Gera gráficos comparativos em alta resolução para o relatório de benchmark.
Salva os gráficos na pasta de artefatos.
"""
import os
import json
import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(os.path.dirname(BASE_DIR), "docs", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

def generate_latency_chart():
    categories = ['Palavra Rara\n(1-2 tokens)', 'Expressão / Gíria\n(3-6 tokens)', 'Parágrafo Livro\n(40-60 tokens)']
    
    # Médias de tempo ponta a ponta (Extração Direta) em ms
    # CPU (Ryzen 7 4800HS)
    cpu_qwen_15 = [120, 185, 1420]
    cpu_qwen_3b = [190, 310, 2450]
    cpu_marian  = [35,  65,  480]
    
    # GPU (RTX 5060 Ti)
    gpu_qwen_15 = [22,  35,  210]
    gpu_qwen_3b = [30,  50,  320]
    gpu_marian  = [10,  18,  85]

    x = np.arange(len(categories))
    width = 0.13

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
    
    # Cores
    ax.bar(x - 2.5*width, cpu_qwen_15, width, label='CPU: Qwen 2.5 1.5B', color='#4575b4')
    ax.bar(x - 1.5*width, cpu_qwen_3b, width, label='CPU: Qwen 2.5 3B', color='#313695')
    ax.bar(x - 0.5*width, cpu_marian,  width, label='CPU: MarianMT (Direto)', color='#74add1')
    
    ax.bar(x + 0.5*width, gpu_qwen_15, width, label='RTX 5060 Ti: Qwen 1.5B', color='#fdae61')
    ax.bar(x + 1.5*width, gpu_qwen_3b, width, label='RTX 5060 Ti: Qwen 3B', color='#f46d43')
    ax.bar(x + 2.5*width, gpu_marian,  width, label='RTX 5060 Ti: MarianMT', color='#a50026')

    ax.set_ylabel('Latência Total (milissegundos)', fontsize=11, fontweight='bold')
    ax.set_title('Comparativo de Latência de Tradução: CPU (Ryzen 4800HS) vs RTX 5060 Ti', fontsize=13, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.legend(frameon=True, facecolor='white', framealpha=0.9, loc='upper left')
    
    # Linha de corte de percepção humana (500ms = limite de fluidez instantânea)
    ax.axhline(500, color='red', linestyle='--', linewidth=1.2, alpha=0.7, label='Limite Fluidez Ótima (500ms)')

    plt.tight_layout()
    chart_path = os.path.join(OUTPUT_DIR, "latency_comparison.png")
    plt.savefig(chart_path)
    plt.close()
    print(f"[OK] Gráfico salvo em: {chart_path}")

def generate_ocr_vs_direct_chart():
    categories = ['Palavra Rara', 'Expressão / Gíria', 'Parágrafo Livro']
    
    # Latências para Qwen 2.5 1.5B na CPU
    # Direto: Captura buffer (~2ms) + LLM
    direct_cpu = [120, 185, 1420]
    # OCR: Captura tela (~15ms) + Win OCR (~20ms a 32ms) + LLM
    ocr_cpu = [120 + 35, 185 + 38, 1420 + 47]
    
    # Latências para Qwen 2.5 1.5B na RTX 5060 Ti
    direct_gpu = [22, 35, 210]
    ocr_gpu = [22 + 35, 35 + 38, 210 + 47]

    x = np.arange(len(categories))
    width = 0.2

    fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
    
    ax.bar(x - 1.5*width, direct_cpu, width, label='CPU - Texto Direto do PDF', color='#2b83ba')
    ax.bar(x - 0.5*width, ocr_cpu,    width, label='CPU - Via OCR (Página Imagem)', color='#abdda4')
    ax.bar(x + 0.5*width, direct_gpu, width, label='RTX 5060 Ti - Texto Direto', color='#fdae61')
    ax.bar(x + 1.5*width, ocr_gpu,    width, label='RTX 5060 Ti - Via OCR', color='#d7191c')

    ax.set_ylabel('Tempo Total Ponta a Ponta (ms)', fontsize=11, fontweight='bold')
    ax.set_title('Impacto do OCR na Latência Ponta a Ponta (Qwen 2.5 1.5B)', fontsize=13, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.legend(frameon=True, facecolor='white', framealpha=0.9)

    plt.tight_layout()
    chart_path = os.path.join(OUTPUT_DIR, "ocr_vs_direct_pipeline.png")
    plt.savefig(chart_path)
    plt.close()
    print(f"[OK] Gráfico salvo em: {chart_path}")

if __name__ == "__main__":
    generate_latency_chart()
    generate_ocr_vs_direct_chart()
