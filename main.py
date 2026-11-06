import os
import sys
from pathlib import Path
import logging


def startup_log():
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    data=Path(os.environ.get('LOCALCLIPS_DATA',str(root/'data')))
    try:
        data.mkdir(parents=True,exist_ok=True)
    except OSError:
        data=Path(os.environ.get('LOCALAPPDATA',str(root)))/'LocalClipsAI'
        data.mkdir(parents=True,exist_ok=True)
        os.environ['LOCALCLIPS_DATA']=str(data)
    handler=logging.FileHandler(data/'startup.log',encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger=logging.getLogger('startup')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info('Start executable=%s frozen=%s cwd=%s',sys.executable,getattr(sys,'frozen',False),Path.cwd())
    def failure(kind,value,trace):
        logger.critical('Unhandled startup/runtime exception',exc_info=(kind,value,trace))
        if sys.__excepthook__:
            sys.__excepthook__(kind,value,trace)
    sys.excepthook=failure
    return logger

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    logger=startup_log()
    # PyInstaller uses this path for both the GUI and the cancellable worker.
    if "--worker" in sys.argv:
        # Windowed PyInstaller apps have no Python stdout/stderr, but QProcess
        # supplies real Windows pipe handles for worker mode.
        for name, handle_id in (("stdout", -11), ("stderr", -12)):
            stream = getattr(sys, name)
            if stream is None and os.name == "nt":
                import ctypes
                import msvcrt
                get_handle = ctypes.windll.kernel32.GetStdHandle
                get_handle.restype = ctypes.c_void_p
                descriptor = msvcrt.open_osfhandle(get_handle(handle_id), os.O_WRONLY)
                setattr(sys, name, os.fdopen(descriptor, "w", encoding="utf-8", buffering=1))
            elif stream is not None:
                stream.reconfigure(encoding="utf-8")
        from localclips.worker import main
        raise SystemExit(main(sys.argv[sys.argv.index("--worker") + 1]))
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if "--self-test-gui" in sys.argv:
        # Test the actual frozen GUI, not only headless workers. Persist failures
        # instead of showing the PyInstaller fatal-error dialog in automated tests.
        import json
        import traceback
        from pathlib import Path
        report = Path(sys.argv[sys.argv.index("--self-test-gui") + 1])
        try:
            from localclips.gui_check import check
            raise SystemExit(check(report))
        except Exception:
            report.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
            raise SystemExit(1)
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    try:
        from localclips.ui import run
        logger.info('Qt and GUI modules imported successfully')
        raise SystemExit(run())
    except Exception:
        logger.exception('GUI initialization failed')
        raise
