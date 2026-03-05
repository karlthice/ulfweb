"""Update service for ULF Web — scan USB drives, apply code updates, import models."""

import json
import logging
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from backend.config import settings
from backend.services.backup_service import backup_service

logger = logging.getLogger("ulfweb")

VERSION_FILE = Path(__file__).parent.parent.parent / "VERSION"
PROJECT_ROOT = Path(__file__).parent.parent.parent
STAGING_DIR = Path("data/update-staging")

# Items to replace during a code update (relative to project root)
REPLACEABLE_ITEMS = [
    "backend",
    "frontend",
    "requirements.txt",
    "VERSION",
    "install.sh",
    "docs",
    "scripts",
    "Caddyfile",
    "ulfweb.service",
    "ulfweb-caddy.service",
]

# Items that are never touched during an update
PROTECTED_ITEMS = {"config.yaml", "data", ".venv", "venv", ".git", "models", "CLAUDE.md"}


class UpdateService:
    """Manages USB-based code updates and model imports."""

    def get_current_version(self) -> str:
        """Read the current version from the VERSION file."""
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text().strip()
        return "0.0.0"

    def scan_media_mounts(self) -> list[dict]:
        """Scan /media/<user>/ and /run/media/<user>/ for mounted USB drives."""
        drives = []
        scan_dirs = []

        # Linux: /media/<user>/ mounts
        media_dir = Path("/media")
        if media_dir.exists():
            for user_dir in media_dir.iterdir():
                if user_dir.is_dir():
                    scan_dirs.append(user_dir)

        # Some distros use /run/media/<user>/
        run_media_dir = Path("/run/media")
        if run_media_dir.exists():
            for user_dir in run_media_dir.iterdir():
                if user_dir.is_dir():
                    scan_dirs.append(user_dir)

        for parent in scan_dirs:
            try:
                for mount_point in parent.iterdir():
                    if mount_point.is_dir() and os.access(mount_point, os.R_OK):
                        drives.append({
                            "name": mount_point.name,
                            "path": str(mount_point),
                        })
            except PermissionError:
                continue

        return drives

    def scan_update_packages(self, usb_path: str) -> list[dict]:
        """Find ulfweb-update-*.tar.gz files on a USB drive and parse their manifests."""
        usb = Path(usb_path)
        if not usb.exists() or not usb.is_dir():
            return []

        packages = []
        for f in sorted(usb.glob("ulfweb-update-*.tar.gz")):
            try:
                manifest = self._read_manifest(f)
                if manifest:
                    packages.append({
                        "filename": f.name,
                        "path": str(f),
                        "size": f.stat().st_size,
                        "version": manifest.get("version", "unknown"),
                        "date": manifest.get("date", ""),
                        "description": manifest.get("description", ""),
                    })
            except Exception as e:
                logger.warning("Failed to read manifest from %s: %s", f, e)
                # Still list the package but without manifest info
                packages.append({
                    "filename": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "version": "unknown",
                    "date": "",
                    "description": "(could not read manifest)",
                })

        return packages

    def _read_manifest(self, tar_path: Path) -> dict | None:
        """Read manifest.json from a tar.gz without full extraction."""
        with tarfile.open(str(tar_path), "r:gz") as tar:
            try:
                member = tar.getmember("manifest.json")
                f = tar.extractfile(member)
                if f:
                    return json.loads(f.read())
            except KeyError:
                return None
        return None

    def scan_models(self, usb_path: str) -> list[dict]:
        """Find .gguf model files in <usb_path>/models/."""
        models_dir = Path(usb_path) / "models"
        if not models_dir.exists() or not models_dir.is_dir():
            return []

        models = []
        for f in sorted(models_dir.glob("*.gguf")):
            models.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
            })

        return models

    def apply_code_update(self, package_path: str) -> dict:
        """Apply a code update from a tar.gz package.

        Steps:
        1. Validate package (manifest, no path traversal)
        2. Create backup
        3. Extract code/ into staging dir
        4. Swap replaceable items (current → .update-old, staged → current)
        5. Run pip install -r requirements.txt
        6. Clean up staging and .update-old
        7. Return result

        On failure after step 4: rollback by restoring .update-old items.
        """
        pkg = Path(package_path)
        if not pkg.exists():
            raise FileNotFoundError(f"Update package not found: {package_path}")

        if not tarfile.is_tarfile(str(pkg)):
            raise ValueError(f"Not a valid tar archive: {package_path}")

        # Step 1: Validate
        with tarfile.open(str(pkg), "r:gz") as tar:
            members = tar.getmembers()

            # Check for path traversal
            for member in members:
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(f"Package contains unsafe path: {member.name}")

            # Check manifest exists
            member_names = [m.name for m in members]
            if "manifest.json" not in member_names:
                raise ValueError("Package missing manifest.json")

            # Check code/ directory exists
            has_code = any(n.startswith("code/") for n in member_names)
            if not has_code:
                raise ValueError("Package missing code/ directory")

        # Read manifest for version info
        manifest = self._read_manifest(pkg)
        new_version = manifest.get("version", "unknown") if manifest else "unknown"

        # Step 2: Create backup
        logger.info("Creating pre-update backup...")
        try:
            backup_result = backup_service.create_backup()
            logger.info("Pre-update backup created: %s", backup_result["filename"])
        except Exception as e:
            raise RuntimeError(f"Failed to create pre-update backup: {e}") from e

        # Step 3: Extract code/ into staging dir
        staging = STAGING_DIR
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        try:
            with tarfile.open(str(pkg), "r:gz") as tar:
                # Only extract members under code/
                code_members = [m for m in tar.getmembers() if m.name.startswith("code/")]
                for member in code_members:
                    member_path = Path(member.name)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"Unsafe path in package: {member.name}")
                tar.extractall(path=str(staging), members=code_members)
        except Exception as e:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"Failed to extract update package: {e}") from e

        staged_code = staging / "code"
        if not staged_code.exists():
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError("Extracted package has no code/ directory")

        # Step 4: Swap replaceable items
        swapped = []
        try:
            for item_name in REPLACEABLE_ITEMS:
                staged_item = staged_code / item_name
                current_item = PROJECT_ROOT / item_name
                old_item = PROJECT_ROOT / f"{item_name}.update-old"

                if not staged_item.exists():
                    # This item isn't in the update package, skip it
                    continue

                # Rename current → .update-old (if it exists)
                if current_item.exists():
                    if old_item.exists():
                        # Clean up any leftover .update-old from a previous failed update
                        if old_item.is_dir():
                            shutil.rmtree(old_item)
                        else:
                            old_item.unlink()
                    current_item.rename(old_item)

                # Move staged item into place
                shutil.move(str(staged_item), str(current_item))
                swapped.append(item_name)

            logger.info("Swapped %d items: %s", len(swapped), ", ".join(swapped))

        except Exception as e:
            # Rollback: restore .update-old items
            logger.error("Update failed during swap, rolling back: %s", e)
            self._rollback(swapped)
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"Update failed during file swap: {e}") from e

        # Step 5: Run pip install
        try:
            req_file = PROJECT_ROOT / "requirements.txt"
            if req_file.exists():
                venv_pip = PROJECT_ROOT / ".venv" / "bin" / "pip"
                if not venv_pip.exists():
                    venv_pip = PROJECT_ROOT / "venv" / "bin" / "pip"
                if venv_pip.exists():
                    logger.info("Installing updated requirements...")
                    subprocess.run(
                        [str(venv_pip), "install", "-r", str(req_file), "--quiet"],
                        check=True,
                        timeout=120,
                        capture_output=True,
                    )
        except subprocess.SubprocessError as e:
            logger.warning("pip install failed (update still applied): %s", e)
            # Don't rollback for pip failures — the code is already in place

        # Step 6: Clean up
        shutil.rmtree(staging, ignore_errors=True)
        for item_name in swapped:
            old_item = PROJECT_ROOT / f"{item_name}.update-old"
            if old_item.exists():
                try:
                    if old_item.is_dir():
                        shutil.rmtree(old_item)
                    else:
                        old_item.unlink()
                except OSError as e:
                    logger.warning("Failed to clean up %s: %s", old_item, e)

        logger.info("Code update applied successfully: version %s", new_version)

        return {
            "version": new_version,
            "items_updated": swapped,
            "backup": backup_result["filename"],
            "restarting": True,
        }

    def _rollback(self, swapped: list[str]) -> None:
        """Rollback swapped items by restoring .update-old versions."""
        for item_name in swapped:
            current_item = PROJECT_ROOT / item_name
            old_item = PROJECT_ROOT / f"{item_name}.update-old"

            try:
                # Remove the new (potentially broken) item
                if current_item.exists():
                    if current_item.is_dir():
                        shutil.rmtree(current_item)
                    else:
                        current_item.unlink()

                # Restore old version
                if old_item.exists():
                    old_item.rename(current_item)
                    logger.info("Rolled back: %s", item_name)
            except OSError as e:
                logger.error("Rollback failed for %s: %s", item_name, e)

    def import_model(self, source_path: str) -> dict:
        """Copy a .gguf model file from USB to the configured models directory."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Model file not found: {source_path}")

        if not source.name.endswith(".gguf"):
            raise ValueError("Only .gguf model files can be imported")

        # Determine destination directory from config
        models_paths = settings.models.path
        if not models_paths:
            raise ValueError("No models path configured in config.yaml")

        # Use the first path if comma-separated
        dest_dir = Path(models_paths.split(",")[0].strip())
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file = dest_dir / source.name
        if dest_file.exists():
            raise ValueError(f"Model already exists: {source.name}")

        logger.info("Importing model %s to %s...", source.name, dest_dir)
        shutil.copy2(str(source), str(dest_file))

        size = dest_file.stat().st_size
        logger.info("Model imported: %s (%d bytes)", source.name, size)

        return {
            "filename": source.name,
            "path": str(dest_file),
            "size": size,
        }


# Singleton instance
update_service = UpdateService()
