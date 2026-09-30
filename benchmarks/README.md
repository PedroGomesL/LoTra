# LoTra - Benchmarks

Estrutura organizada de benchmarks de OCR, tradução contextual e resiliência de hardware.

## Estrutura do Diretório

```
benchmarks/
├── data/              # Conjuntos de dados e geradores de páginas de teste
│   ├── dataset.json
│   ├── a4_ground_truth.json
│   ├── generate_complex_a4.py
│   └── generate_test_pages.py
├── results/           # Resultados consolidados e canônicos em JSON
│   ├── master_benchmark_results.json
│   ├── ocr_benchmark_results.json
│   ├── llm_translation_results.json
│   ├── academic_articles_benchmark_results.json
│   ├── advanced_stress_benchmark_results.json
│   ├── benchmark_llm_vs_marian.json
│   └── benchmark_results_lighter_models.json
├── runners/           # Scripts de execução de benchmarks
│   ├── run_master_benchmark.py
│   ├── run_ocr_bench.py
│   ├── llm_translation_bench.py
│   └── accuracy_metrics.py
├── visualization/     # Geração de gráficos comparativos
│   ├── generate_advanced_charts.py
│   └── generate_charts.py
└── README.md
```

## Como Executar

### 1. Master Benchmark (Consolidação de OCR, Tradução e Stress)
```bash
python benchmarks/runners/run_master_benchmark.py
```
Gera `benchmarks/results/master_benchmark_results.json`.

### 2. Benchmark de OCR (Windows Media OCR e Layout A4)
```bash
python benchmarks/runners/run_ocr_bench.py
```
Gera `benchmarks/results/ocr_benchmark_results.json`.

### 3. Benchmark de Tradução (Latência CPU vs GPU e Qualidade)
```bash
python benchmarks/runners/llm_translation_bench.py
```
Gera `benchmarks/results/llm_translation_results.json`.

### 4. Geração de Gráficos
```bash
python benchmarks/visualization/generate_advanced_charts.py
python benchmarks/visualization/generate_charts.py
```
Os gráficos de alta resolução são salvos em `docs/images/`.
