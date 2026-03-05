#!/usr/bin/env python3
"""Create an ULF Web update package for USB distribution.

Usage:
    python3 scripts/create_release.py 1.1.0 -d "Bug fixes and new features"

Output: ulfweb-update-v1.1.0.tar.gz in the current directory.
"""

import argparse
import json
import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path

# Items to include in code/ (relative to project root)
INCLUDE_ITEMS = [
    "backend",
    "frontend",
    "docs",
    "scripts",
    "requirements.txt",
    "VERSION",
    "install.sh",
    "Caddyfile",
    "ulfweb.service",
    "ulfweb-caddy.service",
]

# Patterns to exclude within included directories
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".pyo",
    ".DS_Store",
    "Thumbs.db",
}


def should_exclude(path: str) -> bool:
    """Check if a path should be excluded from the archive."""
    parts = Path(path).parts
    for part in parts:
        if part in EXCLUDE_PATTERNS or any(part.endswith(ext) for ext in EXCLUDE_PATTERNS):
            return True
    return False


def create_release(version: str, description: str, output_dir: str = ".") -> str:
    """Create an update tar.gz package."""
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Update VERSION file
    version_file = project_root / "VERSION"
    version_file.write_text(version + "\n")
    print(f"Updated VERSION to {version}")

    # Create manifest
    manifest = {
        "version": version,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "description": description,
    }

    output_path = Path(output_dir) / f"ulfweb-update-v{version}.tar.gz"

    with tarfile.open(str(output_path), "w:gz") as tar:
        # Add manifest.json at the root of the archive
        manifest_json = json.dumps(manifest, indent=2).encode()
        import io
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_json)
        tar.addfile(info, io.BytesIO(manifest_json))

        # Add code/ items
        for item_name in INCLUDE_ITEMS:
            item_path = project_root / item_name
            if not item_path.exists():
                print(f"  Skipping {item_name} (not found)")
                continue

            if item_path.is_file():
                tar.add(str(item_path), arcname=f"code/{item_name}")
                print(f"  Added code/{item_name}")
            elif item_path.is_dir():
                file_count = 0
                for root, dirs, files in os.walk(str(item_path)):
                    # Filter out excluded directories in-place
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS]
                    for f in files:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, str(project_root))
                        if not should_exclude(rel_path):
                            tar.add(full_path, arcname=f"code/{rel_path}")
                            file_count += 1
                print(f"  Added code/{item_name}/ ({file_count} files)")

    size = output_path.stat().st_size
    size_mb = size / 1024 / 1024
    print(f"\nCreated: {output_path} ({size_mb:.1f} MB)")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Create an ULF Web update package")
    parser.add_argument("version", help="Version number (e.g., 1.1.0)")
    parser.add_argument("-d", "--description", default="", help="Update description")
    parser.add_argument("-o", "--output", default=".", help="Output directory")

    args = parser.parse_args()

    # Basic version validation
    parts = args.version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(f"Error: Invalid version format '{args.version}'. Use X.Y.Z (e.g., 1.1.0)")
        sys.exit(1)

    create_release(args.version, args.description, args.output)


if __name__ == "__main__":
    main()
