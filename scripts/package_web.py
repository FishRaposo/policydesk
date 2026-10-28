"""Copy the built static app into generated package resources before uv build."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package_web(root: Path = ROOT) -> None:
    root = root.resolve()
    source = root / "web/dist"
    target = root / "src/policydesk/web_dist"
    if not (source / "index.html").is_file():
        raise ValueError("Run npm ci --prefix web and npm run build --prefix web first")
    if target.is_symlink() or target.resolve() != root / "src/policydesk/web_dist":
        raise ValueError("Generated frontend destination must stay inside this project")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    hashes = {
        p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(target.rglob("*"))
        if p.is_file()
    }
    (target / "build-manifest.json").write_text(
        json.dumps(hashes, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Packaged {len(hashes)} actual frontend assets; no credentials or provider requests")


if __name__ == "__main__":
    package_web()
