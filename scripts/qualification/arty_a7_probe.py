"""Side-effect-free probe for the protected Arty A7 qualification cell."""

from __future__ import annotations

import json
import shutil
import subprocess


def main() -> int:
    executable = shutil.which("vivado")
    version = None
    if executable is not None:
        result = subprocess.run(
            (executable, "-version"),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        version = result.stdout.splitlines()[0] if result.stdout else None
    print(
        json.dumps(
            {
                "schema_version": 1,
                "vivado": {"available": executable is not None, "path": executable, "version": version},
                "board_detected": False,
                "reason": "board discovery requires the protected serial-bound lab runner",
            },
            sort_keys=True,
        )
    )
    return 0 if executable is not None and version and "v2025.2" in version else 2


if __name__ == "__main__":
    raise SystemExit(main())
