import importlib.metadata as md
import json
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "licenses"
root.mkdir(exist_ok=True)
index = []
for dist in md.distributions():
    name = dist.metadata["Name"]
    files = []
    for file in dist.files or []:
        if any(s in str(file).lower() for s in ("license", "copying", "notice")):
            source = Path(dist.locate_file(file))
            if source.is_file():
                # Preserve license trees and their filenames for traceability.
                target = root / name / Path(str(file).replace("..", "_"))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                files.append(str(target.relative_to(root)))
    index.append({"name":name, "version":dist.version,
                  "license":dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See bundled notices",
                  "homepage":dist.metadata.get_all("Project-URL"), "files":files})
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    shutil.copy2(python_license, root / "PYTHON-LICENSE.txt")
(root / "inventory.json").write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Collected licenses from {len(index)} distributions")
