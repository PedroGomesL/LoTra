"""
LoTra - Local Translator & Reader Assistant for Windows.
Ponto de entrada principal da aplicação (CLI / Daemon HUD / Auto-Teste).
"""

import os
import sys
import argparse
import json
from pathlib import Path

# Adiciona diretório src ao path para permitir execução direta ou congelada
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app import LoTraApp

APP_VERSION = "1.0.0"

BANNER = rf"""
========================================================================
   _           _____             
  | |         |_   _|            LoTra v{APP_VERSION} (Windows Standalone)
  | |     ___   | |_ __ __ _     Local Translator & Reader Assistant
  | |    / _ \  | | '__/ _` |    Zero-Leakage • WinRT OCR • Hardware Aware
  | |___| (_) | | | | | (_| |    Privacy-First Document Vault
  \_____/\___/  \_/_|  \__,_|    
========================================================================
"""

def main():
    parser = argparse.ArgumentParser(
        description=f"LoTra v{APP_VERSION} - Local Translator & Reader Assistant for Windows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplos de uso:\n"
               "  LoTra.exe --profile              # Exibe detecção de hardware e tier de IA\n"
               "  LoTra.exe --translate \"hello\"    # Traduz texto direto pelo terminal\n"
               "  LoTra.exe --ocr doc.png          # Extrai texto de imagem com Windows Media OCR\n"
               "  LoTra.exe --process doc.png      # OCR + Tradução ponta a ponta\n"
               "  LoTra.exe --test                 # Executa bateria de auto-testes e diagnóstico\n"
               "  LoTra.exe --gui                  # Inicia serviço de segundo plano com HUD e atalhos Alt+Q e Alt+W\n"
    )

    parser.add_argument("--profile", action="store_true", help="Inspeciona hardware real do sistema (CPU, RAM, GPU) e exibe tier recomendado")
    parser.add_argument("--translate", "-t", type=str, metavar="TEXT", help="Traduz uma frase ou texto do inglês para português")
    parser.add_argument("--ocr", type=str, metavar="IMAGE_PATH", help="Executa OCR nativo do Windows em um arquivo de imagem")
    parser.add_argument("--process", "-p", type=str, metavar="IMAGE_PATH", help="Executa OCR na imagem e traduz o texto extraído")
    parser.add_argument("--test", action="store_true", help="Executa bateria de auto-diagnóstico dos subsistemas")
    parser.add_argument("--gui", "--hud", action="store_true", help="Inicia o HUD Tooltip com escuta dos 2 atalhos: Alt+Q (Seleção) e Alt+W (OCR)")
    parser.add_argument("--version", "-v", action="version", version=f"LoTra v{APP_VERSION}")

    args = parser.parse_args()

    app = LoTraApp()

    if args.profile:
        print(BANNER)
        print(">>> PERFIL DE HARDWARE REAL:")
        hw = app.profile_hardware()
        print(f"  * Sistema Operacional : {hw['os']}")
        print(f"  * Processador (CPU)   : {hw['cpu_cores']} núcleos lógicos (AVX2: {hw['has_avx2']})")
        print(f"  * Memória RAM Física  : {hw['total_ram_gb']} GB (Livre: {hw['avail_ram_gb']} GB | Uso: {hw['ram_used_pct']}%)")
        print(f"  * Placa de Vídeo (GPU): {hw['gpu_name']} ({hw['gpu_backend']})")
        print(f"  * Memória de Vídeo    : {hw['vram_gb']} GB VRAM")
        print(f"  * Tier Recomendado    : {hw['recommended_tier'].upper()} ({hw['recommended_model']})")
        print(f"  * Motivo da Seleção   : {hw['decision_reason']}")
        return 0

    if args.translate:
        res = app.translate_text(args.translate)
        print(BANNER)
        print(">>> RESULTADO DA TRADUÇÃO:")
        print(f"  * Original   : {res['source_text']}")
        print(f"  * Tradução   : {res['translated_text']}")
        print(f"  * Latência   : {res['latency_ms']} ms (Cache Hit: {res['cache_hit']})")
        print(f"  * Motor      : {res['engine_used']}")
        print(f"  * Perfil HW  : {res.get('hardware_profile', 'N/A')}")
        return 0

    if args.ocr:
        res = app.ocr_image(args.ocr)
        print(BANNER)
        print(f">>> OCR WINDOWS MEDIA OCR: {args.ocr}")
        if res.get("success"):
            print(f"  * Sucesso     : Sim")
            print(f"  * Inferência  : {res.get('inference_ms', 0):.1f} ms")
            print(f"  * Pipeline    : {res.get('elapsed_ms', 0):.1f} ms")
            print(f"  * Texto Lido  :\n---")
            print(res.get("text", ""))
            print("---")
            return 0
        else:
            print(f"  [FALHA] {res.get('error', 'Erro desconhecido')}")
            return 1

    if args.process:
        print(BANNER)
        print(f">>> PIPELINE COMPLETO (OCR + TRADUÇÃO): {args.process}")
        res = app.process_image(args.process)
        if res.get("success"):
            ocr = res["ocr"]
            trans = res["translation"]
            print(f"  * Tempo Total : {res['total_pipeline_ms']:.1f} ms")
            print(f"  * OCR Tempo   : {ocr.get('elapsed_ms', 0):.1f} ms")
            print(f"  * Texto OCR   :\n{ocr.get('text', '')}")
            print(f"\n  * Tradução ({trans.get('engine_used')}):")
            print(f"{trans.get('translated_text', '')}")
            return 0
        else:
            print(f"  [FALHA] {res.get('error')}")
            return 1

    if args.test:
        print(BANNER)
        print(">>> EXECUTANDO AUTO-DIAGNÓSTICO E AUTO-TESTE...")
        test_res = app.run_self_test()
        for sub, info in test_res["subsystems"].items():
            status = info["status"]
            icon = "[PASS]" if status == "PASS" else ("[WARN]" if status == "WARN" else "[FAIL]")
            print(f"  {icon} {sub}: {info}")
        
        print("\n========================================================================")
        if test_res["all_passed"]:
            print("TODOS OS SUBSISTEMAS VALIDADOS COM SUCESSO!")
            return 0
        else:
            print("ALGUNS SUBSISTEMAS APRESENTARAM FALHAS OU AVISOS.")
            return 1

    if args.gui or (not args.profile and not args.translate and not args.ocr and not args.process and not args.test):
        # Modo interativo (duplo clique ou --gui): Aplica proteção de instância única
        from platform_core import SingleInstanceGuard
        guard = SingleInstanceGuard()
        if not guard.acquire():
            print("[LoTra] Uma instância do aplicativo já está em execução. Trazendo janela para frente...")
            guard.activate_existing_window("LoTra")
            return 0

        try:
            print(BANNER)
            app.start_hud_service(show_gui=True)
        finally:
            guard.release()
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
