"""
LoTra Windows Builder & Compiler Script:
Compila a aplicação LoTra em um executável standalone nativo para Windows (.exe)
utilizando PyInstaller com suporte a Python 3.14, empacotando assets (ícones, PowerShell WinRT OCR,
recursos de privacidade, banco ACID e orquestrador de IA).
"""

import os
import sys
import shutil
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "lotra.ico"
WIN_OCR_SCRIPT = BASE_DIR / "src" / "win_ocr.ps1"
ENTRY_POINT = BASE_DIR / "main.py"

def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def ensure_assets():
    """Garante que todos os assets obrigatórios existem antes de compilar."""
    print(">>> 1. Verificando assets e scripts do runtime...")
    
    # 1. Ícone
    if not ICON_PATH.exists():
        print(f"  [INFO] Gerando ícone oficial em {ICON_PATH}...")
        gen_script = BASE_DIR / "generate_icon.py"
        if gen_script.exists():
            subprocess.run([sys.executable, str(gen_script)], check=True)
        else:
            raise FileNotFoundError(f"generate_icon.py não encontrado em {gen_script}")
    print(f"  [OK] Ícone localizado: {ICON_PATH}")

    # 2. Script Windows Media OCR
    if not WIN_OCR_SCRIPT.exists():
        raise FileNotFoundError(f"Script win_ocr.ps1 obrigatório não encontrado em: {WIN_OCR_SCRIPT}")
    print(f"  [OK] Script WinRT OCR localizado: {WIN_OCR_SCRIPT}")

def clean_previous_builds():
    """Limpa artefatos temporários de compilações anteriores com encerramento de processos travados."""
    print(">>> 2. Limpando artefatos de compilações anteriores...")
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "LoTra.exe"], capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass

    for p in [BUILD_DIR, DIST_DIR]:
        if p.exists():
            removed = False
            for attempt in range(5):
                try:
                    shutil.rmtree(p)
                    print(f"  [OK] Diretório removido: {p}")
                    removed = True
                    break
                except Exception as e:
                    time.sleep(0.5)
            if not removed:
                print(f"  [WARN] Diretório {p} retido por lock do sistema, prosseguindo com sobrescrita.")

    # Não remove LoTra.spec oficial do repositório
    for spec_file in BASE_DIR.glob("*.spec"):
        if spec_file.name == "LoTra.spec":
            continue
        try:
            spec_file.unlink()
            print(f"  [OK] Spec temporário removido: {spec_file.name}")
        except Exception:
            pass

def run_pyinstaller_build(mode: str = "onefile") -> Path:
    """Executa a compilação do executável com PyInstaller."""
    print_header(f"COMPILANDO STANDALONE WINDOWS (.EXE) - MODO: {mode.upper()}")
    t0 = time.perf_counter()

    spec_path = BASE_DIR / "LoTra.spec"
    if spec_path.exists() and mode == "onefile":
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "LoTra.spec",
            "--noconfirm",
            "--clean"
        ]
    else:
        # Monta comando do PyInstaller dinâmico
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name", "LoTra",
            "--icon", str(ICON_PATH),
            f"--add-data={WIN_OCR_SCRIPT};src",
            f"--add-data={ICON_PATH};assets",
        ]
        if mode == "onefile":
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")

        # Módulos ocultos para garantir empacotamento completo
        hidden_imports = [
            "sqlite3",
            "ctypes",
            "ctypes.wintypes",
            "PIL",
            "PIL.Image",
            "PIL.ImageDraw",
            "PIL.IcoImagePlugin",
            "numpy",
            "urllib.request",
            "urllib.error",
            "tkinter",
            "tkinter.ttk",
            "json",
            "platform",
            "subprocess",
            "dataclasses",
            "hashlib",
            "uuid",
            "threading",
            "app",
            "ocr_engine",
            "translation_engine",
            "hud_tooltip",
            "screen_snipper",
            "resource_utils",
            "platform_core",
            "adaptive_engine_orchestrator",
            "document_context_vault",
            "privacy_vault",
            "incremental_scanner",
            "pdf_resilience_manager"
        ]

        for hi in hidden_imports:
            cmd.extend(["--hidden-import", hi])

        # Adiciona caminhos de busca
        cmd.extend(["--paths", str(BASE_DIR / "src")])
        cmd.extend(["--paths", str(BASE_DIR)])

        # Entry point
        cmd.append(str(ENTRY_POINT))

    print(f"Executando comando de compilação:")
    print(" ".join(cmd[:12]) + " ... [imports e flags]")
    
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise RuntimeError(f"PyInstaller falhou com código de saída {result.returncode}")

    elapsed = time.perf_counter() - t0
    print(f"\n[OK] Compilação concluída com sucesso em {elapsed:.1f} segundos!")

    if mode == "onefile":
        exe_path = DIST_DIR / "LoTra.exe"
    else:
        exe_path = DIST_DIR / "LoTra" / "LoTra.exe"

    if not exe_path.exists():
        raise FileNotFoundError(f"Executável esperado não foi encontrado em: {exe_path}")

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Executável gerado: {exe_path}")
    print(f"[OK] Tamanho final: {size_mb:.2f} MB")
    return exe_path

def verify_executable(exe_path: Path):
    """Executa verificações reais no executável gerado (.exe standalone)."""
    print_header("VERIFICANDO EXECUTÁVEL COMPILADO")

    # 1. Teste de versão
    print(">>> 1. Verificando --version...")
    res = subprocess.run([str(exe_path), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    print(f"  Saída: {res.stdout.strip()}")
    assert res.returncode == 0, f"Falha ao executar --version (código {res.returncode}): {res.stderr}"

    # 2. Teste de Hardware Profiler
    print(">>> 2. Verificando --profile...")
    res_prof = subprocess.run([str(exe_path), "--profile"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    assert res_prof.returncode == 0, f"Falha ao executar --profile: {res_prof.stderr}"
    assert "PERFIL DE HARDWARE REAL" in res_prof.stdout, "Saída inesperada no --profile"
    print("  [PASS] Hardware Profiler respondeu corretamente.")

    # 3. Teste de Auto-Diagnóstico (--test)
    print(">>> 3. Verificando --test (Integridade dos subsistemas empacotados)...")
    res_test = subprocess.run([str(exe_path), "--test"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert res_test.returncode == 0, f"Falha ao executar --test: {res_test.stderr}"
    assert "TODOS OS SUBSISTEMAS VALIDADOS COM SUCESSO!" in res_test.stdout, "Sub-sistemas falharam no teste compilado"
    print("  [PASS] Auto-diagnóstico compilado validado com sucesso!")

    # 4. Teste de Tradução Direta
    print(">>> 4. Verificando --translate 'quantum scalability'...")
    res_trans = subprocess.run([str(exe_path), "--translate", "quantum scalability"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    assert res_trans.returncode == 0, f"Falha ao executar --translate: {res_trans.stderr}"
    assert "escalabilidade" in res_trans.stdout.lower() or "quântic" in res_trans.stdout.lower(), f"Tradução esperada não encontrada na saída: {res_trans.stdout}"
    print("  [PASS] Pipeline de Tradução respondeu com sucesso!")

    # 5. Teste de OCR Nativo WinRT com UTF-8
    sample_img = BASE_DIR / "docs" / "images" / "latency_comparison.png"
    if sample_img.exists():
        print(f">>> 5. Verificando --ocr com amostra real ({sample_img.name})...")
        res_ocr = subprocess.run([str(exe_path), "--ocr", str(sample_img)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        assert res_ocr.returncode == 0, f"Falha ao executar --ocr: {res_ocr.stderr}"
        assert "Latência de Tradução" in res_ocr.stdout or "Lat" in res_ocr.stdout, "Texto OCR não reconhecido"
        assert "\ufffd" not in res_ocr.stdout, "Detectado caractere corrompido (mojibake) na saída OCR"
        print("  [PASS] Windows Media OCR nativo executado e decodificado com UTF-8 perfeito!")

    print_header("TODAS AS VERIFICAÇÕES DO EXECUTÁVEL PASSARAM COM 100% DE SUCESSO!")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LoTra Windows Compiler & Standalone Packager")
    parser.add_argument("--mode", choices=["onefile", "onedir"], default="onefile", help="Modo de compilação (padrão: onefile)")
    parser.add_argument("--no-verify", action="store_true", help="Pula os testes de validação pós-compilação")
    args = parser.parse_args()

    print_header(f"LOTRA BUILD SYSTEM - PYTHON {sys.version.split()[0]} WINDOWS")
    ensure_assets()
    clean_previous_builds()
    exe = run_pyinstaller_build(mode=args.mode)
    if not args.no_verify:
        verify_executable(exe)

    print("\nExecutável pronto para distribuição em:")
    print(f"  file:///{str(exe).replace(os.sep, '/')}\n")

if __name__ == "__main__":
    main()
