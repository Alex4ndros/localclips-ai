# Contributing to LocalClips AI

Contributi, issue e pull request sono benvenuti in italiano e in inglese.
Issues and pull requests in Italian or English are welcome. This is a Windows
desktop application for turning local recordings into editable vertical clips.

## Development setup

1. Fork the repository, clone your fork and create a branch for your change.
2. Install Python **3.12 x64** on Windows 11.
3. Create a virtual environment and install the tested dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1
.\.venv\Scripts\python.exe main.py
```

You can supply your own FFmpeg/FFprobe in `tools/` or PATH instead of downloading
the pinned build. Required capabilities: H.264 via libx264, AAC and libass subtitles.
The lock file includes optional NVIDIA runtimes and packaging tools; installation
is large. A GPU is not required for the test suite or manual composition.
Download Whisper through the application's Settings only when testing transcription.
The small MIT-licensed YuNet detector is included for face-detection tests.

## Checks before a pull request

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests create synthetic media in temporary folders and inspect exported pixels,
audio, caption timing, persistence and cancellation. The NASA face fixture has
its attribution in `tests/assets/README.md`. OAuth tests use generated test keys
and a loopback server; they require localhost TCP access but no real account,
paid API or external inference. Whisper failure handling uses a test double.
The full suite does not require a downloaded Whisper model.

For rendering changes, inspect actual exported frames as well as test results.
For Qt or packaging changes, build on Windows and verify the actual EXE:

```powershell
.\.venv\Scripts\python.exe scripts/collect_licenses.py
.\.venv\Scripts\python.exe scripts/build.py
.\.venv\Scripts\python.exe scripts/generate_examples.py
.\.venv\Scripts\python.exe scripts/validate_portable.py C:/LocalClips-Portable-Test --exclusion
```

Choose a writable test folder outside your checkout. The script copies the
bundle there, launches its GUI with a clean PATH and exercises import, preview
and export. `validate_inference.py` and `validate_bundle.py` are additional local
hardware checks, requiring Whisper Small, CUDA/NVENC and the speech fixture
described by those scripts; they are not part of the regular CI suite.
Generated reports, videos and build products are intentionally untracked.

## Project layout

| Module | Responsibility |
| --- | --- |
| `localclips/ui.py`, `preview.py`, `timeline.py` | Qt interface, live preview, editing |
| `domain.py` | Project data, validation and persistence |
| `reframing.py` | Shared deterministic crop/composition geometry |
| `media.py`, `subtitles.py` | FFmpeg export and ASS/SRT subtitles |
| `vision.py` | Webcam detection and tracking proposals |
| `transcription.py`, `selection.py`, `semantic.py` | Local transcription and clip suggestions |
| `jobs.py`, `worker.py` | Background processing and cancellation |
| `auth.py`, `credentials.py` | Optional authentication and Windows-protected tokens |

## Scope and review

- Start with an issue for substantial architecture or workflow changes.
- Keep pull requests focused. Explain the concrete problem, resulting behavior,
  tests performed and any limitations; include synthetic before/after frames
  when changing video composition.
- Preserve offline operation and make external AI use explicit and optional.
- Use the shared geometry for preview and export. Keep lengthy work off the GUI
  thread, preserve cancellation, and handle missing GPU/native dependencies.
- Never commit real credentials, personal recordings, transcripts, `.lcproj`
  files, local paths from logs, or private test data. Use synthetic fixtures.
- Include attribution and licensing information for any new third-party assets.
- Don't describe features or tests as working unless you have verified them.

Useful contribution areas include Italian transcription evaluation, accessible
editor controls, reproducible packaging, safer automatic webcam detection,
clip-selection quality and the incomplete features documented in `STATUS.md`.

Be respectful and discuss changes on their technical merits. Contributions to
the original source are made under the project's MIT license; third-party
components retain their own licenses. See `LICENSE.txt` and
`THIRD_PARTY_NOTICES.md` before distributing binary bundles.
