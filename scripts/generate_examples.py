"""Generate non-sensitive OBS fixtures for manual and portable GUI checks."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from test_reframing import synthetic_desktop


def main():
    app = QApplication.instance() or QApplication([])
    for name, full in (('smart-split', False), ('no-duplicate', True)):
        folder = root / 'examples' / name
        folder.mkdir(parents=True, exist_ok=True)
        # Existing examples may have project references; never overwrite them.
        if (folder / 'source-1440p.mp4').exists():
            print(f'Keeping existing {name}/source-1440p.mp4')
            continue
        generated = synthetic_desktop(folder, full_desktop=full)
        destination = folder / 'source-1440p.mp4'
        generated.rename(destination)
        print(destination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
