"""Copy already built UI assets into their owning Python wheel package data."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for ui, service, package in [
    ("mock-c4i", "mock-c4i", "mock_c4i"),
    ("mock-atcis", "mock-atcis", "mock_atcis"),
    ("mock-knccs", "mock-knccs", "mock_knccs"),
    ("platform-web", "platform-api", "platform_api"),
    ("data-fabric-web", "semantic-api", "semantic_api"),
]:
    source = ROOT / "frontend" / "apps" / ui / "dist"
    target = ROOT / "services" / service / "src" / package / "web_static"
    if not (source / "index.html").exists():
        raise SystemExit(f"Build frontend first: missing {source / 'index.html'}")
    # Keep the target constrained to this service's generated asset directory.
    if not target.resolve().is_relative_to(ROOT / "services"):
        raise SystemExit("Invalid static asset target")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    print(f"Packaged {ui} -> {target.relative_to(ROOT)}")
