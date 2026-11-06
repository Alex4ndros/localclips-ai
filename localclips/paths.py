import os
import sys
from pathlib import Path


def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def data_root():
    root = Path(os.environ.get("LOCALCLIPS_DATA", str(app_root() / "data")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def models_root():
    root = app_root() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def setup_cuda_paths():
    """Opt-in native libraries placed alongside the portable app or installed by pip."""
    candidates = [app_root() / "cuda"]
    base = Path(getattr(sys, "_MEIPASS", Path(sys.prefix) / "Lib" / "site-packages"))
    for name in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
        candidates.extend([base / "nvidia" / name / "bin", base / "nvidia" / name / "lib"])
    handles = []
    for folder in candidates:
        if folder.is_dir():
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                handles.append(os.add_dll_directory(str(folder)))
    return handles
