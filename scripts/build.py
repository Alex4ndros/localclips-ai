"""Run with the locked Python 3.12 environment; creates a portable onedir build."""
import hashlib
import os
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = Path(os.environ.get("LOCALCLIPS_DIST_DIR", str(ROOT / "dist")))
BUILD = Path(os.environ.get("LOCALCLIPS_BUILD_DIR", str(ROOT / "build")))


def main():
    staging = BUILD / 'staging'
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
               "--name", "LocalClipsAI", "--distpath", str(staging), "--workpath", str(BUILD), "--specpath", str(BUILD),
               "--collect-data", "faster_whisper", "--collect-all", "ctranslate2", "--collect-all", "onnxruntime",
               "--copy-metadata", "huggingface-hub", "--exclude-module", "PySide6.QtWebEngineCore",
               "--exclude-module", "PySide6.QtWebEngineWidgets", str(ROOT / "main.py")]
    environment = os.environ.copy()
    # Do not let unrelated developer tools (Poppler, libheif, other Qt installs)
    # supply same-named native DLLs during PyInstaller dependency resolution.
    windows = Path(environment.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
        Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs", windows / "System32", windows]))
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYTHONPATH"):
        environment.pop(key, None)
    subprocess.run(command, cwd=ROOT, check=True, env=environment)
    target = staging / "LocalClipsAI"
    # This Windows 11 build uses the OS ICU ABI. A renamed third-party icuuc.dll
    # exporting ucnv_open_78 instead of ucnv_open must never enter this bundle.
    if (target / "_internal" / "icuuc.dll").exists():
        raise RuntimeError("Unexpected bundled ICU DLL: verify its origin before distribution.")
    for directory in ("tools", "models", "licenses"):
        if (ROOT / directory).is_dir():
            shutil.copytree(ROOT / directory, target / directory, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".cache", "*.lock"))
    # NVIDIA runtimes stay replaceable and separate from the application binary.
    native = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if native.is_dir():
        (target / "cuda").mkdir(exist_ok=True)
        for package in ("cublas", "cudnn", "cuda_nvrtc"):
            for dll in (native / package / "bin").glob("*.dll"):
                if ".alt." not in dll.name:
                    shutil.copy2(dll, target / "cuda" / dll.name)
    for filename in ("README.md", "STATUS.md", "WEBCAM-FIX.md", "THIRD_PARTY_NOTICES.md", "LICENSE.txt", "requirements-lock.txt"):
        if (ROOT / filename).is_file():
            shutil.copy2(ROOT / filename, target / filename)
    # Mandatory regression test: the headless analysis worker does not import Qt.
    report = BUILD / "gui-startup.json"
    test_env = environment.copy()
    test_env["LOCALCLIPS_DATA"] = str(BUILD / "gui-test-data")
    result = subprocess.run([str(target / "LocalClipsAI.exe"), "--self-test-gui", str(report)],
                            env=test_env, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not report.exists() or not json.loads(report.read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError(f"Frozen GUI startup failed; see {report}")
    manifest = {}
    for file in sorted(target.rglob("*")):
        if file.is_file():
            with file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            manifest[str(file.relative_to(target))] = {"bytes":file.stat().st_size, "sha256":digest}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2),encoding="utf-8")
    # Promote only after startup passes. Preserve user data, projects, exports
    # and downloaded models; back up the previous native runtime for recovery.
    destination=(DIST/'LocalClipsAI').resolve()
    internal=(destination/'_internal').resolve()
    backup=(BUILD/('previous-runtime-'+str(time.time_ns()))).resolve()
    if not internal.is_relative_to(DIST.resolve()) or not backup.is_relative_to(BUILD.resolve()):
        raise RuntimeError('Unsafe build destination')
    if internal.exists():
        shutil.move(str(internal),str(backup))
    try:
        shutil.copytree(target,destination,dirs_exist_ok=True)
    except Exception:
        if not internal.exists() and backup.exists():
            shutil.move(str(backup),str(internal))
        raise
    print(f"Distribution: {destination}")


if __name__ == "__main__":
    main()
