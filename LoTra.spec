# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import subprocess

BASE_DIR = os.path.abspath(SPECPATH)
MAIN_PY = os.path.join(BASE_DIR, 'main.py')
SRC_DIR = os.path.join(BASE_DIR, 'src')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ICON_FILE = os.path.join(ASSETS_DIR, 'lotra.ico')
WIN_OCR_FILE = os.path.join(SRC_DIR, 'win_ocr.ps1')

# Geração automática de ícone se ausente
if not os.path.exists(ICON_FILE):
    gen_icon = os.path.join(BASE_DIR, 'generate_icon.py')
    if os.path.exists(gen_icon):
        try:
            subprocess.run([sys.executable, gen_icon], check=True)
        except Exception as e:
            print(f"[LoTra Spec] Aviso ao gerar ícone: {e}")

debug_console = os.environ.get('LOTRA_DEBUG_CONSOLE', '0').strip().lower() in ('1', 'true', 'yes')

a = Analysis(
    [MAIN_PY],
    pathex=[SRC_DIR, BASE_DIR],
    binaries=[],
    datas=[
        (WIN_OCR_FILE, 'src'),
        (ICON_FILE, 'assets'),
        (os.path.join(ASSETS_DIR, 'lotra.png'), 'assets')
    ],
    hiddenimports=[
        'sqlite3', 'ctypes', 'ctypes.wintypes', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
        'PIL.IcoImagePlugin', 'PIL.ImageTk', 'numpy', 'urllib.request', 'urllib.error', 'tkinter',
        'tkinter.ttk', 'json', 'platform', 'subprocess', 'dataclasses', 'hashlib',
        'uuid', 'threading', 'queue', 'app', 'ocr_engine', 'translation_engine', 'hud_tooltip',
        'screen_snipper', 'resource_utils', 'platform_core', 'adaptive_engine_orchestrator',
        'document_context_vault', 'privacy_vault', 'incremental_scanner',
        'pdf_resilience_manager', 'ui_window'
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'torch', 'transformers', 'tokenizers', 'safetensors', 'sympy', 'jinja2',
        'pandas', 'matplotlib', 'seaborn', 'shiny', 'shinychat', 'huggingface_hub',
        'optimum', 'ctranslate2', 'scipy', 'pyarrow'
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LoTra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=debug_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_FILE],
)
