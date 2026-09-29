# -*- mode: python ; coding: utf-8 -*-
import os

BASE_DIR = os.path.abspath(SPECPATH)
MAIN_PY = os.path.join(BASE_DIR, 'main.py')
SRC_DIR = os.path.join(BASE_DIR, 'src')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ICON_FILE = os.path.join(ASSETS_DIR, 'lotra.ico')
WIN_OCR_FILE = os.path.join(SRC_DIR, 'win_ocr.ps1')

a = Analysis(
    [MAIN_PY],
    pathex=[SRC_DIR, BASE_DIR],
    binaries=[],
    datas=[
        (WIN_OCR_FILE, 'src'),
        (ICON_FILE, 'assets')
    ],
    hiddenimports=[
        'sqlite3', 'ctypes', 'ctypes.wintypes', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
        'PIL.IcoImagePlugin', 'numpy', 'urllib.request', 'urllib.error', 'tkinter',
        'tkinter.ttk', 'json', 'platform', 'subprocess', 'dataclasses', 'hashlib',
        'uuid', 'threading', 'app', 'ocr_engine', 'translation_engine', 'hud_tooltip',
        'resource_utils', 'platform_core', 'adaptive_engine_orchestrator',
        'document_context_vault', 'privacy_vault', 'incremental_scanner',
        'pdf_resilience_manager'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_FILE],
)
