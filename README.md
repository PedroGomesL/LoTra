<div align="center">
  <img src="assets/lotra.png" alt="LoTra Logo" width="140" />
  <h1>LoTra</h1>
  <p><strong>Local Translator & Reader</strong></p>
  <p>Assistente local e offline de leitura e tradução (Inglês → Português Brasileiro) para Windows com OCR e contexto de documentos.</p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" /></a>
    <img src="https://img.shields.io/badge/Platform-Windows%2010%2B-0078d4.svg" alt="Platform: Windows" />
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776ab.svg" alt="Python 3.10+" />
    <img src="https://img.shields.io/badge/Privacy-100%25%20Offline-2ea44f.svg" alt="Privacy: Offline" />
  </p>
</div>

---

## Visão Geral

O **LoTra** auxilia na leitura de artigos técnicos, livros e documentos em inglês sem necessidade de alternar janelas ou depender de serviços em nuvem. Ele roda em segundo plano e apresenta traduções instantâneas em uma interface flutuante (HUD).

### Comandos Principais

| Atalho | Ação |
| :---: | :--- |
| **`Alt + Q`** | **Traduzir seleção**: copia a seleção atual automaticamente e exibe a tradução com ajuste de quebras de linha de PDFs. |
| **`Alt + W`** | **Traduzir via OCR**: aciona o recorte de tela do Windows ou processa imagem copiada para extrair texto e traduzir. |
| **`Esc`** | Fecha a janela flutuante de tradução. |

---

## Funcionalidades

- **Tradução Offline e Adaptativa**: dicionário técnico e acadêmico local com regras morfológicas, cache SQLite e suporte a modelos neurais locais (ONNX / Ollama).
- **OCR Integrado**: utiliza o Windows Media OCR nativo (DirectML / WinRT) sem necessidade de dependências pesadas, com filtro para remoção de marca-texto.
- **Princípio Read-Only**: nenhuma alteração é feita nos diretórios dos documentos lidos; metadados e cache residem exclusivamente em `%LOCALAPPDATA%\LoTra\`.
- **Identificação por Fingerprint**: arquivos movidos ou renomeados mantêm histórico e contexto via hash dos primeiros 64 KB.
- **Interface Flutuante (HUD)**: tooltip translúcido com tipografia ajustada para leitura contínua e suporte a múltiplos monitores.

---

## Estrutura do Repositório

```text
LoTra/
├── assets/                  # Ícones e logotipo oficial (PNG, ICO)
├── benchmarks/              # Suíte de benchmarks e métricas
│   ├── data/                # Datasets e geradores de documentos sintéticos
│   ├── results/             # Resultados canônicos em JSON
│   ├── runners/             # Scripts de execução (master, OCR, LLM)
│   ├── visualization/       # Geradores de gráficos comparativos
│   └── README.md            # Documentação dos benchmarks
├── docs/                    # Documentação técnica e relatórios de arquitetura
├── scripts/                 # Scripts de build e utilitários
│   ├── build_windows.ps1    # Script PowerShell para compilação
│   ├── build_windows.py     # Script Python do PyInstaller
│   └── generate_icon.py     # Gerador dos assets gráficos do projeto
├── src/                     # Código-fonte da aplicação
│   ├── adaptive_engine_orchestrator.py
│   ├── app.py
│   ├── document_context_vault.py
│   ├── hud_tooltip.py
│   ├── incremental_scanner.py
│   ├── ocr_engine.py
│   ├── offline_dictionary.py
│   ├── pdf_resilience_manager.py
│   ├── platform_core.py
│   ├── privacy_vault.py
│   ├── resource_utils.py
│   ├── screen_snipper.py
│   ├── translation_engine.py
│   ├── ui_window.py
│   └── win_ocr.ps1
├── tests/                   # Bateria de testes automatizados
│   ├── unit/                # Testes unitários (tradução, morfologia, interface)
│   ├── integration/         # Testes de integração (segurança, arquitetura, app)
│   ├── stress/              # Testes de carga e saturação de recursos
│   └── simulation/          # Simulação com documentos PDF reais
├── LoTra.spec               # Configuração do PyInstaller
├── main.py                  # Ponto de entrada da aplicação
├── requirements.txt         # Dependências do projeto
└── README.md
```

---

## Instalação e Uso

### Requisitos
- Windows 10 ou 11 (64 bits)
- Python 3.10 ou superior

### Configuração do Ambiente

```bash
git clone https://github.com/PedroGomesL/LoTra.git
cd LoTra

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

### Executar a Aplicação

```bash
python main.py
```

Ou usando o executável compilado:
```bash
.\dist\LoTra.exe
```

---

## Testes

Para executar toda a suíte de testes (unitários, integração, stress e simulação):

```bash
python -m unittest discover tests
```

Para executar categorias específicas:

```bash
# Testes unitários
python -m unittest discover tests/unit

# Testes de integração
python -m unittest discover tests/integration

# Testes de estresse
python -m unittest discover tests/stress

# Simulação de leitura de PDFs
python -m unittest discover tests/simulation
```

---

## Compilação Standalone (.exe)

O projeto pode ser empacotado em um único executável standalone para Windows:

```bash
# Via Python
python scripts/build_windows.py

# Via PowerShell
powershell -File scripts/build_windows.ps1
```

O binário final é gerado em `dist/LoTra.exe`.

---

## Licença

Este projeto é disponibilizado sob a licença [MIT](LICENSE).
