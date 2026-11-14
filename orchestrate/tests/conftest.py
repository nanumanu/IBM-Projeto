"""Deixa orchestrate/ no sys.path para os testes importarem safeone_tools sem instalar nada.

Esta pasta não tem __init__.py de propósito: assim ela não vira um pacote "tests" e não
entra em conflito com o pacote tests/ da raiz do repositório.
"""
import sys
from pathlib import Path

ORCHESTRATE_DIR = str(Path(__file__).resolve().parents[1])
if ORCHESTRATE_DIR not in sys.path:
    sys.path.insert(0, ORCHESTRATE_DIR)
