# LoTra (Local Translator & Reader) 📖⚡

> **Leitor e Tradutor Instantâneo Local (Inglês $\rightarrow$ Português Brasileiro) com OCR de Baixa Latência, Princípio Read-Only e Contexto Global.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2B-blue.svg)](https://www.microsoft.com)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Offline%20%7C%20Zero%20Telemetry-green.svg)]()
[![Inference](https://img.shields.io/badge/Inference-GGUF%20%7C%20DirectML%20%7C%20CUDA-purple.svg)]()

---

## 🌟 O que é o LoTra?

Ler livros técnicos, artigos acadêmicos ou ficção em inglês no computador costuma ser interrompido por um ciclo cansativo: encontrar uma palavra ou expressão desconhecida, alternar de janela (`Alt+Tab`), colar no tradutor web, esperar a resposta, ler e voltar para a leitura. Esse atrito quebra o **ritmo de leitura** (*flow state*).

O **LoTra** foi concebido como um software executável autônomo para Windows (`.exe`), operando em segundo plano:
1. **Modo Direto (`Alt+Q`)**: Selecione qualquer palavra, frase ou expressão em um PDF ou livro digital e visualize um HUD translúcido instantâneo ao lado do cursor com a tradução contextualizada e direta em Português do Brasil.
2. **Modo OCR (`Alt+S`)**: Para livros escaneados, PDFs sem camada de texto ou imagens com diagramas técnicos, ative a mira de recorte: o motor extrai o texto em **menos de 30 ms** e exibe a tradução sem sair da página.

---

## 🚀 Principais Funcionalidades

### 1. ⚡ Inferência Local Ultrarrápida e Ajuste Adaptativo
- **PC com GPU Fraca / CPU Pura (ex: Ryzen 4800HS)**: Roda modelos otimizados via instruções vetoriais AVX2 (`Qwen 2.5 1.5B` ou `MarianMT`), respondendo entre **120 ms e 180 ms**.
- **PC com GPU Dedicada (ex: NVIDIA RTX 5060 Ti)**: Aceleração total via CUDA Tensor Cores (`Qwen 2.5 3B / 7B`), traduzindo em **20 ms a 50 ms**.
- **VRAM Cleanup Ativo**: Descarrega pesos da GPU após uso para não monopolizar a placa de vídeo durante jogos ou tarefas pesadas.

### 2. 👁️ Subsistema de OCR de Duplo Estágio
- **Windows Media OCR (Nativo WinRT / DirectML)**: Zero dependências externas de download, latência imbatível de **16 ms a 28 ms**.
- **RapidOCR (ONNX Runtime)**: Fallback de alta precisão para digitalizações antigas com inclinação ou ruído de granulação.
- **Supressão de Marca-Texto**: Filtro espectral HSV que neutraliza canetas fluorescentes (amarelo, verde, rosa, laranja) e entrega caracteres pretos nítidos ao OCR.

### 3. 🛡️ Segurança, Privacidade e Princípio Read-Only Estrito
- **Zero Poluição de Diretórios**: O aplicativo **nunca escreve** nos diretórios ou no NAS/NFS onde os livros residem (sem pastas `.cache`, `.sherlock` ou `@eaDir`).
- **Isolamento de Estado**: 100% dos dados, índices e configurações ficam estritamente em `%LOCALAPPDATA%\LoTra\`.
- **Anti-Vazamento (Zero-Disk Leaks)**: Capturas de tela e páginas renderizadas transitam exclusivamente em memória RAM (`io.BytesIO`) e sofrem higienização forçada de memória (*memory wiping*) imediatamente após a extração.

### 4. 🧠 Contexto Global do Documento (Sem Proliferação de Arquivos)
- **Arquivo Único SQLite WAL (`reader_vault.db`)**: Centraliza metadados, títulos, resumos de introdução e vocabulário sem criar milhares de arquivos soltos.
- **Invariância de Movimentação (SHA-256 64KB)**: Se você renomear um livro ou movê-lo de pasta, o sistema detecta a identidade do arquivo instantaneamente, preservando o histórico de traduções sem reprocessamento.
- **Injeção Hierárquica**: Alimenta a LLM com um prefixo conciso do assunto do livro, garantindo traduções com a acepção correta para termos polissêmicos.

### 5. 🔍 Scan Incremental & Cancelamento Cooperativo
- **Fase de Descoberta Rápida**: Compara `mtime` e tamanho em lote (300 arquivos validados em 78 ms).
- **Checkpoints Persistentes**: Salva o cursor de varredura no banco para retomar exatamente de onde parou em caso de queda de energia ou fechamento inesperado.
- **Cancelamento Cooperativo**: Responde em menos de **1 segundo** ao comando do usuário.

---

## 📊 Benchmarks de Performance

Resultados medidos em testes reais na CPU (AMD Ryzen 7 4800HS 8c/16t, 20GB RAM) e modelados para RTX 5060 Ti:

| Operação | Modo de Entrada | Tempo no PC Fraco (CPU) | Tempo na RTX 5060 Ti (CUDA) | Taxa de Acerto |
| :--- | :--- | :---: | :---: | :---: |
| **Palavra Isolada** | Texto Direto (PDF Nativo) | **~120 ms** | **~22 ms** | 100.0% |
| **Palavra Isolada** | Via OCR (Livro Escaneado) | **~151 ms** | **~55 ms** | 100.0% |
| **Expressão / Idiom** | Texto Direto | **~185 ms** | **~35 ms** | 100.0% |
| **Expressão / Idiom** | Via OCR | **~215 ms** | **~68 ms** | 100.0% |
| **Parágrafo Literário** | Texto Direto | **~1.42 s** | **~210 ms** | 100.0% |
| **Parágrafo Literário** | Via OCR | **~1.45 s** | **~257 ms** | 99.7% |
| **Página A4 Completa** | OCR de Página com Diagramas | **~183 ms** | **~45 ms** | 6/6 caixas de diagrama |

---

## 🏗️ Estrutura do Repositório

```text
LoTra/
├── src/
│   ├── core/
│   │   ├── adaptive_engine_orchestrator.py # Detecção de hardware e seleção de SLA
│   │   ├── document_context_vault.py       # Cofre SQLite WAL e injeção de contexto
│   │   ├── incremental_scanner.py          # Scanner incremental em duas fases
│   │   ├── pdf_resilience_manager.py       # Carving de streams e montagem de 2 páginas
│   │   └── privacy_vault.py                # Wiping de memória e proteção DPAPI
│   ├── ocr/
│   │   ├── win_media_ocr.py                # Wrapper WinRT / DirectML nativo do Windows
│   │   └── rapid_ocr_engine.py             # Motor ONNX Runtime para fallback
│   ├── translation/
│   │   ├── llm_engine.py                   # Runtime GGUF (llama.cpp) / DirectML / CUDA
│   │   └── prompt_templates.py             # Prompts de tradução direta sem enrolação
│   └── ui/
│       ├── hud_tooltip.py                  # Popup flutuante translúcido (PyQt6 / WinUI)
│       └── snip_overlay.py                 # Máscara de seleção de recorte em tela
├── tests/
│   ├── test_security_privacy_scanner.py    # Suíte com 11 testes de segurança e scan
│   └── test_system_architecture.py         # Testes de orquestrador, SLA e resiliência
├── docs/
│   ├── benchmark_report.md                 # Relatório quantitativo completo com gráficos
│   └── security_architecture.md            # Especificação de segurança e isolamento
├── LICENSE
└── README.md
```

---

## 🔧 Como Executar

### Pré-requisitos
- **Windows 10 ou 11 (64-bit)**
- **Python 3.10+** (para execução a partir do código-fonte)
- Acelerador gráfico (Opcional): Placa de vídeo NVIDIA com suporte a CUDA para o modo de alta performance.

### Instalação

```bash
# Clone o repositório
git clone https://github.com/PedroGomesL/LoTra.git
cd LoTra

# Crie e ative um ambiente virtual
python -m venv venv
venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

### Executando os Testes Automatizados

```bash
# Executa a suíte de testes de segurança, privacidade e scan incremental
python tests/test_security_privacy_scanner.py

# Executa os testes de arquitetura e resiliência de hardware
python tests/test_system_architecture.py
```

---

## ⌨️ Atalhos Padrão

| Atalho | Ação |
| :---: | :--- |
| `Alt + Q` | Tradução instantânea do texto selecionado na tela |
| `Alt + S` | Abre a ferramenta de recorte para OCR em PDFs escaneados ou imagens |
| `Esc` | Fecha o popup de tradução instantânea |

---

## 📄 Licença

Distribuído sob a licença **MIT**. Veja `LICENSE` para mais informações.
