"""pytest configuration for the EigenTrace suite.

Runs before any test module is imported:
  * CUDA_VISIBLE_DEVICES="" is set BEFORE torch is imported anywhere, so every
    torch call in the suite (calculate_svd_reconstruction, sentence_transformers
    import) stays on the CPU and never touches the GPU the live broadcast owns.
  * The repo root is put on sys.path so `import batch_producer` etc. work when
    pytest is run from the root (`python3 -m pytest tests -q`).
  * `dotenv` is replaced by a no-op stub.  proxy_auditor.py and batch_producer.py
    call load_dotenv(<repo>/.env) at import time; the tests need no API key and
    must never pull secrets into the test process.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

# 1. GPU off, before torch can be imported by any module under test.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
assert "torch" not in sys.modules, "torch was imported before conftest set CUDA_VISIBLE_DEVICES"

# 2. Repo root importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 3. No-op dotenv so .env is never read into os.environ by module imports.
if "dotenv" not in sys.modules:
    _stub = types.ModuleType("dotenv")
    _stub.load_dotenv = lambda *a, **k: False          # type: ignore[attr-defined]
    _stub.find_dotenv = lambda *a, **k: ""             # type: ignore[attr-defined]
    _stub.dotenv_values = lambda *a, **k: {}           # type: ignore[attr-defined]
    _stub.__stub__ = True                              # type: ignore[attr-defined]
    sys.modules["dotenv"] = _stub
