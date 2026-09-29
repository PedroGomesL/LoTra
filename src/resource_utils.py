"""
Utilitário de resolução de caminhos de recursos para desenvolvimento e runtime congelado (PyInstaller / Nuitka).
"""

import os
import sys
from pathlib import Path

def get_resource_path(relative_path: str) -> Path:
    """
    Retorna o caminho absoluto do recurso solicitado.
    Suporta:
    1. Executável congelado por PyInstaller (sys._MEIPASS).
    2. Ambiente de desenvolvimento (raiz do repositório ou pasta src).
    3. Executável congelado por cx_Freeze ou Nuitka.
    """
    rel = Path(relative_path)
    
    # 1. PyInstaller _MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_path = Path(sys._MEIPASS) / rel
        if meipass_path.exists():
            return meipass_path
        # Tenta também dentro de src se rel foi passado sem prefixo
        meipass_src = Path(sys._MEIPASS) / "src" / rel
        if meipass_src.exists():
            return meipass_src

    # 2. Diretório do executável (onedir ou binários adjacentes)
    exe_dir = Path(sys.executable).parent
    candidate_exe = exe_dir / rel
    if candidate_exe.exists():
        return candidate_exe
        
    # 3. Diretório raiz do projeto (desenvolvimento)
    # Este arquivo está em src/resource_utils.py, então parent.parent é a raiz do projeto
    current_dir = Path(__file__).resolve().parent
    repo_root = current_dir.parent
    
    candidate_root = repo_root / rel
    if candidate_root.exists():
        return candidate_root
        
    candidate_src = current_dir / rel
    if candidate_src.exists():
        return candidate_src

    # Fallback: retorna caminho normalizado relativo ao CWD
    return Path(os.path.abspath(str(rel)))
