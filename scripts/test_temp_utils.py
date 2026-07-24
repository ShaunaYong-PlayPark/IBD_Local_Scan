import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_TEMP_ROOT = REPO_ROOT / ".tmp"


@contextmanager
def repo_temp_dir(prefix):
    REPO_TEMP_ROOT.mkdir(exist_ok=True)
    path = REPO_TEMP_ROOT / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        resolved_root = REPO_TEMP_ROOT.resolve()
        resolved_path = path.resolve()
        if resolved_root == resolved_path or resolved_root not in resolved_path.parents:
            raise RuntimeError(f"Refusing to clean unsafe temp path: {resolved_path}")
        shutil.rmtree(resolved_path, ignore_errors=True)
