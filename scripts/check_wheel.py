"""Create an isolated install of the built wheel, then check its local runtime."""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uv", default=shutil.which("uv"))
    args = parser.parse_args()
    if not args.uv:
        raise SystemExit("Provide --uv with the installed uv executable path")
    wheel = sorted((ROOT / "dist").glob("policydesk-0.2.0.dev1-*.whl"))[-1]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "policydesk/web_dist/index.html" in names
        assert not any(
            any(p in n.split("/") for p in (".runtime", ".venv", "node_modules", ".git"))
            for n in names
        )
    environment = ROOT / ".runtime/wheel-installed"
    subprocess.run(
        [args.uv, "venv", "--allow-existing", "--python", sys.executable, str(environment)],
        check=True,
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            args.uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--reinstall-package",
            "policydesk",
            f"policydesk[live] @ {wheel.as_uri()}",
        ],
        check=True,
    )
    cwd = ROOT / ".runtime/wheel-cwd-v2"
    cwd.mkdir(exist_ok=True)
    subprocess.run(
        [str(python), "-I", str(ROOT / "scripts/check_installed.py")], cwd=cwd, check=True
    )
    print(f"Installed interpreter for browser checks: {python}")


if __name__ == "__main__":
    main()
