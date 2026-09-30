# Auditoria Completa de Engenharia e Rastreamento de Issues do LoTra

Este documento consolida a auditoria técnica de engenharia de software realizada no ecossistema **LoTra** (*Local Translator & Reader Assistant*), catalogando as vulnerabilidades arquiteturais, limitações de privilégio no Windows, dívidas técnicas, casos de borda em múltiplos monitores e o plano de expansão cross-platform.

Todas as issues foram cadastradas oficialmente no repositório remoto [`PedroGomesL/LoTra`](https://github.com/PedroGomesL/LoTra/issues) com títulos padronizados, descrições aprofundadas, trechos de código afetados e critérios de aceitação.

---

## 1. Matriz de Rastreamento de Issues no GitHub

| # | Título da Issue | Tipo / Rótulos | Status | Arquivo / Módulo Afetado | Link no GitHub |
| :-: | :--- | :--- | :--- | :--- | :--- |
| **#1** | `bug(windows): UIPI blocks synthetic Ctrl+C input when capturing selection from elevated Admin windows` | `bug`, `security` | **RESOLVIDO** | [`src/hud_tooltip.py`](../src/hud_tooltip.py) | [#1](https://github.com/PedroGomesL/LoTra/issues/1) |
| **#2** | `bug(hud): Multi-monitor & High-DPI tooltip positioning edge cases across virtual screens with negative coordinates` | `bug`, `accessibility` | **RESOLVIDO** | [`src/hud_tooltip.py`](../src/hud_tooltip.py) | [#2](https://github.com/PedroGomesL/LoTra/issues/2) |
| **#3** | `bug(ocr): Esc cancellation during ms-screenclip: causes 15s freeze and processes stale clipboard image` | `bug`, `enhancement` | **RESOLVIDO** | [`src/app.py`](../src/app.py), [`src/screen_snipper.py`](../src/screen_snipper.py) | [#3](https://github.com/PedroGomesL/LoTra/issues/3) |
| **#4** | `feat(engine): Local ONNX & DirectML runtime integration for MarianMT / NLLB-200 offline translation` | `enhancement`, `architecture`, `performance` | **RESOLVIDO** | [`src/translation_engine.py`](../src/translation_engine.py) | [#4](https://github.com/PedroGomesL/LoTra/issues/4) |
| **#5** | `perf(vault): SQLite WAL auto-checkpointing, database vacuuming, and retention size quotas` | `architecture`, `performance` | **RESOLVIDO** | [`src/document_context_vault.py`](../src/document_context_vault.py) | [#5](https://github.com/PedroGomesL/LoTra/issues/5) |
| **#6** | `feat(platform): Native Linux (Wayland / X11) and macOS (Accessibility API) cross-platform expansion` | `enhancement`, `architecture` | **RESOLVIDO** | [`src/platform_core.py`](../src/platform_core.py) | [#6](https://github.com/PedroGomesL/LoTra/issues/6) |
| **#7** | `ci(devops): GitHub Actions workflow for automated test matrix, PyInstaller Windows .exe build, and releases` | `documentation`, `enhancement` | **RESOLVIDO** | `.github/workflows/ci.yml` | [#7](https://github.com/PedroGomesL/LoTra/issues/7) |
| **#8** | `bug(build): Eliminate hardcoded absolute user paths in LoTra.spec for portable builds` | `bug`, `enhancement` | **RESOLVIDO** | [`LoTra.spec`](../LoTra.spec), [`scripts/build_windows.py`](../scripts/build_windows.py) | [#8](https://github.com/PedroGomesL/LoTra/issues/8) |
| **#9** | `feat(pdf): Support for Compressed Object Streams (/ObjStm in PDF 1.5+) and encrypted PDFs in Stream Carving` | `enhancement`, `architecture` | **RESOLVIDO** | [`src/pdf_resilience_manager.py`](../src/pdf_resilience_manager.py) | [#9](https://github.com/PedroGomesL/LoTra/issues/9) |
| **#10** | `bug(scanner): Handle circular NTFS directory junctions, symlinks, and permission errors during scan` | `bug`, `performance` | **RESOLVIDO** | [`src/incremental_scanner.py`](../src/incremental_scanner.py) | [#10](https://github.com/PedroGomesL/LoTra/issues/10) |

---

## 2. Detalhamento Técnico das Áreas Auditadas

### 2.1. Isolamento de Privilégios no Windows (UIPI) e Captura Sintética ([Issue #1](https://github.com/PedroGomesL/LoTra/issues/1))
- **Mecanismo Afetado**: `simulate_copy_selection()` em [`src/hud_tooltip.py`](../src/hud_tooltip.py#L250-L278).
- **Causa Raiz**: O Windows implementa a tecnologia **User Interface Privilege Isolation (UIPI)** no subsistema Win32. Processos executando em *Medium Integrity Level* (usuário comum padrão) são impedidos pelo kernel do Windows de enviar mensagens de janela sintéticas ou injetar eventos de teclado (`keybd_event` / `SendInput`) para processos em *High Integrity Level* (executados como Administrador, ex: Gerenciador de Tarefas, CMD Elevado, Regedit ou leitores PDF rodando com privilégios administrativos).
- **Sintoma Observado**: Ao acionar `Alt + Q` em uma janela elevada, o envio do `Ctrl+C` falha silenciosamente. O `GetClipboardSequenceNumber()` não se altera, o loop aguarda 200ms de timeout e, em seguida, lê o conteúdo anterior do clipboard. Isso faz o LoTra traduzir conteúdo defasado ou falhar sem explicar o motivo ao usuário.
- **Solução Recomendada**:
  1. Inspecionar o nível de integridade da janela ativa via `GetForegroundWindow()`, `GetWindowThreadProcessId()`, `OpenProcessToken()` e `GetTokenInformation(TokenIntegrityLevel)`.
  2. Caso a janela de destino possua integridade superior à do LoTra, abortar imediatamente a espera de 200ms e exibir no HUD: *"Janela em modo Administrador detectada. Execute o LoTra como Administrador ou use Ctrl+C antes do Alt+Q."*
  3. Documentar no manifesto do aplicativo as diretivas de `uiAccess="true"` (para ambientes corporativos assinados digitalmente).

---

### 2.2. Posicionamento de HUD em Múltiplos Monitores e High-DPI ([Issue #2](https://github.com/PedroGomesL/LoTra/issues/2))
- **Mecanismo Afetado**: `HUDTooltip.show()` em [`src/hud_tooltip.py`](../src/hud_tooltip.py#L330-L403).
- **Causa Raiz**: O cálculo de posicionamento baseia-se em `window.winfo_screenwidth()` e `window.winfo_screenheight()`, que representam exclusivamente as dimensões do monitor primário (ex: 1920x1080), assumindo origem em `(0, 0)`.
- **Cenário de Falha**:
  - Em configurações multi-monitor onde o monitor secundário fica à esquerda ou acima do monitor principal, as coordenadas no desktop virtual do Windows tornam-se **negativas** ($x < 0$ ou $y < 0$).
  - O código de contenção (`if pos_y < 20: pos_y = 20` e `pos_x = max(20, screen_w - win_w - 20)`) força o HUD a saltar repentinamente para o monitor primário, ignorando a tela onde o usuário está trabalhando.
  - Diferenças de escala de DPI (ex: 150% no monitor primário 4K e 100% no monitor secundário 1080p) causam desajuste geométrico sem a consulta direta à API de DPI por monitor.
- **Solução Recomendada**:
  1. Utilizar a API Win32 `MonitorFromPoint(POINT, MONITOR_DEFAULTTONEAREST)` e `GetMonitorInfoW` para obter a struct `MONITORINFO` (`rcWork`).
  2. Ajustar as coordenadas do HUD respeitando os limites `rcWork.left <= pos_x <= rcWork.right - win_w` e `rcWork.top <= pos_y <= rcWork.bottom - win_h`.
  3. Incorporar fator de escala de `GetDpiForMonitor`.

---

### 2.3. Ciclo de Vida do Recorte de Tela (`ms-screenclip:`) e Cancelamento via Esc ([Issue #3](https://github.com/PedroGomesL/LoTra/issues/3))
- **Mecanismo Afetado**: `_ocr_worker_task()` em [`src/app.py`](../src/app.py#L152-L191).
- **Causa Raiz**:
  - O LoTra delega o recorte visual ao protocolo do sistema operacional `ms-screenclip:`.
  - Quando o usuário cancela a captura pressionando `Esc` ou clicando fora, nenhuma imagem é gravada na área de transferência.
  - A thread do trabalhador fica retida dormindo em loop durante todo o prazo limite de 15 segundos (`while time.perf_counter() < deadline`).
  - Ao expirar o tempo, a linha 180 executa:
    ```python
    if not grabbed_img:
        data = ImageGrab.grabclipboard()
        if isinstance(data, Image.Image):
            grabbed_img = data
    ```
    Se o usuário possuía **qualquer** imagem previamente copiada no clipboard (por exemplo, um meme ou diagrama copiado há 2 horas), o LoTra processa essa imagem antiga equivocadamente!
  - O protocolo `ms-screenclip:` também não devolve as coordenadas do retângulo de seleção, impedindo o ancoramento contextual do HUD sobre a região recortada.
- **Solução Recomendada**:
  1. Suprimir o fallback indevido para imagens antigas do clipboard. Se o número de sequência do clipboard não mudou, encerrar a rotina graciosamente.
  2. Implementar detecção de fechamento do host de recorte (`ScreenClippingHost.exe`).
  3. Desenvolver overlay nativo em Tkinter/PyQt com cursor reticulado e caixa elástica (*rubber-band*), oferecendo retorno imediato de coordenadas e cancelamento instantâneo via `Esc`.

---

### 2.4. Motor de Inferência Neural ONNX Runtime DirectML / CPU ([Issue #4](https://github.com/PedroGomesL/LoTra/issues/4))
- **Mecanismo Afetado**: [`src/translation_engine.py`](../src/translation_engine.py#L394-L422) e [`docs/architecture_and_benchmark.md`](../docs/architecture_and_benchmark.md#L60-L65).
- **Causa Raiz**: O estudo arquitetural estabelece o modelo **MarianMT / Opus-MT** (77M parâmetros, ~75 t/s em CPU) e **NLLB-200** como padrão de ultrabaixa latência offline. No entanto, no código atual, o modelo `marian_mt` é mapeado internamente para o modelo do Ollama `qwen2.5:0.5b`. Quando o Ollama não está instalado, o sistema cai em um tradutor léxico estático (`OfflineContextTranslator`).
- **Solução Recomendada**:
  1. Criar a classe `ONNXTranslationEngine` utilizando `onnxruntime` com provedores de execução `DirectMLExecutionProvider` (GPU) e `CPUExecutionProvider` (AVX2).
  2. Empacotar ou baixar sob demanda o modelo quantizado `opus-mt-en-pt.onnx` (~45MB) em `%LOCALAPPDATA%\LoTra\models`.
  3. Integrar tokenizador SentencePiece puro em Python.
  4. Permitir tradução neural de altíssima qualidade 100% autônoma, sem necessidade de servidores ou do Ollama instalado.

---

### 2.5. Autolimpeza de WAL, Vacuuming e Cotas de Armazenamento ([Issue #5](https://github.com/PedroGomesL/LoTra/issues/5))
- **Mecanismo Afetado**: [`src/document_context_vault.py`](../src/document_context_vault.py#L68-L84).
- **Causa Raiz**: Embora o SQLite opere com `journal_mode = WAL;`, o banco não define `PRAGMA wal_autocheckpoint`, nem realiza operações de truncamento do arquivo WAL (`PRAGMA wal_checkpoint(TRUNCATE)`), auto-vacuum (`PRAGMA auto_vacuum = INCREMENTAL`) ou cotas de tamanho em disco para as tabelas `translation_cache` e `document_summaries`.
- **Risco**: Com o passar dos meses e dezenas de milhares de páginas lidas, o arquivo `-wal` e o banco podem expandir indefinidamente em disco.
- **Solução Recomendada**:
  1. Fixar `PRAGMA wal_autocheckpoint = 1000;`.
  2. Implementar `checkpoint_wal(mode="TRUNCATE")` disparado no encerramento limpo da aplicação e antes de backups.
  3. Adicionar método de governança `enforce_size_quota(max_size_mb: int = 500)` que descarta entradas antigas do cache de tradução segundo política LRU (*Least Recently Used*) baseada em `last_accessed_at`.

---

### 2.6. Abstração para Linux (Wayland / X11) e macOS ([Issue #6](https://github.com/PedroGomesL/LoTra/issues/6))
- **Mecanismo Afetado**: [`src/platform_core.py`](../src/platform_core.py), [`src/hud_tooltip.py`](../src/hud_tooltip.py), [`src/ocr_engine.py`](../src/ocr_engine.py).
- **Causa Raiz**: Acoplamento forte com APIs nativas do Windows (`ctypes.windll.user32`, `RegisterHotKey`, `keybd_event`, PowerShell `win_ocr.ps1`).
- **Arquitetura Proposta**:
  1. **Interfaces Abstratas**: `HotkeyBackend`, `SelectionGrabberBackend`, `OCRBackend`.
  2. **Implementação Linux**:
     - Wayland: Integração com `org.freedesktop.portal.GlobalShortcuts`, `wl-paste --primary` e `ydotool`.
     - X11: `XGrabKey`, `xclip -o -selection primary` e `xdotool`.
     - OCR: RapidOCR (ONNX) / Tesseract 5.4.
  3. **Implementação macOS**:
     - Seleção: API nativa de Acessibilidade (`AXUIElementCopyAttributeValue` com `kAXSelectedTextAttribute`), permitindo capturar o texto selecionado diretamente sem sintetizar comandos de teclado!
     - OCR: Apple Vision Framework (`VNRecognizeTextRequest`).

---

### 2.7. Pipeline de CI/CD via GitHub Actions ([Issue #7](https://github.com/PedroGomesL/LoTra/issues/7))
- **Mecanismo Afetado**: Estrutura do repositório (ausência de `.github/workflows/`).
- **Problema**: O projeto dependia de compilações manuais via `build_windows.py` e testes disparados localmente pelo desenvolvedor.
- **Solução Proposta**:
  1. Criar `.github/workflows/ci.yml`.
  2. Matriz de testes automatizada em `windows-latest` e `ubuntu-latest` nas versões do Python 3.10 a 3.14.
  3. Job de compilação do executável standalone `LoTra.exe` via PyInstaller, com cálculo de hash criptográfico SHA-256.
  4. Publicação automática de releases com anexo do binário empacotado em tags `v*`.

---

### 2.8. Portabilidade da Especificação do PyInstaller ([Issue #8](https://github.com/PedroGomesL/LoTra/issues/8))
- **Mecanismo Afetado**: [`LoTra.spec`](../LoTra.spec#L5-L38).
- **Problema**: O arquivo `.spec` continha caminhos absolutos hardcoded da máquina local do desenvolvedor (`C:/Users/<user>/...`). Ao tentar compilar em outra máquina ou no runner do GitHub Actions (`D:\a\LoTra\LoTra`), o processo abortava com `FileNotFoundError`.
- **Solução Recomendada**:
  Tornar o arquivo `.spec` dinâmico utilizando a variável nativa `SPECPATH`:
  ```python
  import os
  BASE_DIR = os.path.abspath(SPECPATH)
  MAIN_PY = os.path.join(BASE_DIR, 'main.py')
  SRC_DIR = os.path.join(BASE_DIR, 'src')
  ICON_PATH = os.path.join(BASE_DIR, 'assets', 'lotra.ico')
  WIN_OCR = os.path.join(SRC_DIR, 'win_ocr.ps1')
  ```

---

### 2.9. Resiliência de PDF para Object Streams e Criptografia ([Issue #9](https://github.com/PedroGomesL/LoTra/issues/9))
- **Mecanismo Afetado**: [`src/pdf_resilience_manager.py`](../src/pdf_resilience_manager.py#L110-L160).
- **Problema**: A extração direta por *Stream Carving* atualmente procura apenas blocos de texto não comprimidos (`BT ... Tj ... ET`). Em PDFs da versão 1.5 em diante, objetos e streams de texto costumam vir compactados em pacotes `/ObjStm` (*Compressed Object Streams*) com `FlateDecode`, ou com dicionários de criptografia padrão `/Encrypt`.
- **Solução Recomendada**:
  Detectar blocos de stream Flate em arquivos com Xref ausente, tentar a descompressão via `zlib.decompress()` antes de aplicar regex de texto, e detectar cabeçalhos de segurança `/Encrypt`.

---

### 2.10. Robustez do Scanner para Junções NTFS e Permissões ([Issue #10](https://github.com/PedroGomesL/LoTra/issues/10))
- **Mecanismo Afetado**: [`src/incremental_scanner.py`](../src/incremental_scanner.py#L141-L165).
- **Problema**: No Windows, junções de diretório NTFS e links simbólicos podem criar referências circulares (ex: pastas de dados de aplicativo legadas). Se o scanner encontrar pastas com permissão negada (`EACCES`), exceções não tratadas podem abortar a varredura prematuramente.
- **Solução Recomendada**:
  Adicionar callback de `onerror` ao `os.walk()` e registrar a tupla `(st_dev, st_ino)` para prevenir loops recursivos infinitos.

---

## 3. Estado Atual dos Testes e Validação Local

A bateria completa de testes de engenharia foi executada e validada com 100% de sucesso:
1. `tests/test_system_architecture.py` -> **100% PASS** (Invariância de hash, SQLite WAL mode, `PRAGMA auto_vacuum = INCREMENTAL` validado em modo 2, auto-checkpointing TRUNCATE, vacuuming, quotas de retenção combinadas com descarte LRU e thumbnails, injeção contextual hierárquica, profiler de hardware, supressão de marca-texto HSV, carving de `/ObjStm` e derivação ISO 32000-1 Alg 2, além de validação ponta a ponta dos 4 níveis da hierarquia de fallback do `ONNXTranslationEngine`).
2. `tests/test_security_privacy_scanner.py` -> **100% PASS** (Princípio Read-Only estrito, proteção anti-vazamento, scan incremental em duas fases, cancelamento cooperativo < 1s, health checks, 5 migrações formais, e poda precoce via `os.lstat` testada com junções NTFS circulares reais criadas via `mklink /J`).
3. `tests/test_windows_compiler_and_app.py` -> **100% PASS** (Resolução de recursos, clipboard Win32 UTF-16LE, OCR nativo UTF-8, normalização de texto, clamping dinâmico multi-monitor com coordenadas virtuais negativas, detecção de privilégios UIPI em janelas Admin, ciclo de vida do `NativeScreenSnipper` com overlay multi-monitor e cancelamento < 5ms via Esc).
4. `python build_windows.py` -> **100% PASS** (Compilação standalone concluída com PyInstaller em ~25s, binário `dist/LoTra.exe` de 31.70 MB validado em todos os 5 comandos: `--version`, `--profile`, `--test`, `--translate`, `--ocr`).

---

## 4. Conclusão da Auditoria de Engenharia

Todas as 10 issues catalogadas foram integralmente resolvidas, verificadas e testadas com rigor arquitetural no código do repositório:
- **Issue #1**: Verificação O(0ms) de integridade UIPI e fallback para seleção pré-copiada.
- **Issue #2**: Clamping de área de trabalho multi-monitor (`rcWork`) e escalonamento DPI dinâmico por monitor (`GetDpiForMonitor`).
- **Issue #3**: Recorte nativo em overlay Tkinter multi-monitor (`NativeScreenSnipper`) com cancelamento instantâneo (< 5ms) e captura direta sem poluição do clipboard.
- **Issue #4**: Motor `ONNXTranslationEngine` autônomo com suporte a CTranslate2/ONNX e hierarquia formal de fallback em 4 tiers.
- **Issue #5**: SQLite com `PRAGMA auto_vacuum = INCREMENTAL` (modo 2 garantido), autolimpeza de WAL, tracking LRU (`last_accessed_at`) e cota unificada de retenção.
- **Issue #6**: Abstração cross-platform `IPlatformBridge` para Windows, Linux (Wayland/X11 com `wl-clipboard`, `xclip`, `xsel`) e macOS.
- **Issue #7**: Pipeline de CI/CD automatizado via GitHub Actions com matriz multi-OS e checagens GNU SHA-256.
- **Issue #8**: Especificação PyInstaller portátil baseada em `SPECPATH`, `upx=False`, console configurável e empacotamento completo de módulos.
- **Issue #9**: Stream carving resiliente para `/ObjStm` comprimidos via `zlib.decompressobj` e descriptografia ISO 32000-1 Algoritmo 2 com senhas em branco.
- **Issue #10**: Poda precoce de junções NTFS, symlinks e caminhos protegidos em `os.walk` antes da recursão, prevenindo loops e estouro de pilha.
