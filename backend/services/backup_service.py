"""Backup service for ULF Web — create, restore, rotate, and schedule backups."""

import asyncio
import logging
import os
import tarfile
import tempfile
from datetime import datetime, date
from pathlib import Path

from backend.config import settings
from backend.encryption import is_encrypted, get_db_key

logger = logging.getLogger("ulfweb")

DEFAULT_BACKUP_DIR = Path("data/backups")
BACKUP_PREFIX = "ulfweb-backup-"

# Directories/files to include (relative to project root)
BACKUP_ITEMS = [
    "data/encryption.key",
    "data/vault",
    "data/uploads",
    "data/meeting_chunks",
]


class BackupService:
    """Manages backup creation, restoration, rotation, and scheduling."""

    def __init__(self):
        self.last_error: str | None = None
        self.last_failure_time: str | None = None
        self.last_success_time: str | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._running = False
        self._backup_in_progress = False

    def get_health(self) -> dict:
        """Return backup health status for the banner."""
        return {
            "ok": self.last_error is None,
            "last_error": self.last_error,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }

    def create_backup(self, destination_dir: str | None = None) -> dict:
        """Create a tar.gz backup archive.

        Returns metadata dict with filename, path, size, and items.
        """
        dest = Path(destination_dir) if destination_dir else DEFAULT_BACKUP_DIR
        dest.mkdir(parents=True, exist_ok=True)

        # Validate destination is writable
        if not os.access(dest, os.W_OK):
            raise PermissionError(f"Destination directory is not writable: {dest}")

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"{BACKUP_PREFIX}{timestamp}.tar.gz"
        archive_path = dest / filename

        db_path = Path(settings.database.path)
        db_snapshot = None
        items_included = []

        try:
            # Create a safe DB snapshot using VACUUM INTO
            db_snapshot = tempfile.NamedTemporaryFile(
                suffix=".db", delete=False, dir=str(dest)
            )
            db_snapshot.close()
            snapshot_path = db_snapshot.name

            self._vacuum_into(db_path, snapshot_path)
            items_included.append("ulfweb.db")

            with tarfile.open(archive_path, "w:gz") as tar:
                # Add database snapshot
                tar.add(snapshot_path, arcname="ulfweb.db")

                # Add other items
                for item in BACKUP_ITEMS:
                    item_path = Path(item)
                    if item_path.exists():
                        tar.add(str(item_path), arcname=item)
                        items_included.append(item)

        finally:
            # Clean up snapshot
            if db_snapshot and os.path.exists(db_snapshot.name):
                os.unlink(db_snapshot.name)

        size = archive_path.stat().st_size

        # Clear failure state on success
        self.last_error = None
        self.last_failure_time = None
        self.last_success_time = datetime.now().isoformat()

        logger.info(
            "Backup created: %s (%d bytes, %d items)",
            archive_path, size, len(items_included),
        )
        return {
            "filename": filename,
            "path": str(archive_path),
            "size": size,
            "items": items_included,
        }

    def _vacuum_into(self, db_path: Path, dest_path: str) -> None:
        """Create a consistent DB snapshot using VACUUM INTO."""
        if is_encrypted():
            from sqlcipher3 import dbapi2 as sqlcipher
            conn = sqlcipher.connect(str(db_path))
            hex_key = get_db_key()
            conn.execute(f"PRAGMA key=\"x'{hex_key}'\"")
        else:
            import sqlite3
            conn = sqlite3.connect(str(db_path))

        try:
            conn.execute(f"VACUUM INTO '{dest_path}'")
        finally:
            conn.close()

    def list_backups(self, directory: str | None = None) -> list[dict]:
        """List backup archives in the given or default directory."""
        scan_dir = Path(directory) if directory else DEFAULT_BACKUP_DIR
        if not scan_dir.exists():
            return []

        backups = []
        for f in scan_dir.glob(f"{BACKUP_PREFIX}*.tar.gz"):
            stat = f.stat()
            backups.append({
                "filename": f.name,
                "path": str(f),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        backups.sort(key=lambda b: b["modified"], reverse=True)
        return backups

    def validate_backup(self, path: str) -> dict:
        """Validate a backup archive and return its contents."""
        backup_path = Path(path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {path}")

        if not tarfile.is_tarfile(str(backup_path)):
            raise ValueError(f"Not a valid tar archive: {path}")

        with tarfile.open(str(backup_path), "r:gz") as tar:
            members = tar.getnames()

        has_db = "ulfweb.db" in members
        return {
            "valid": has_db,
            "has_database": has_db,
            "contents": members,
            "filename": backup_path.name,
            "size": backup_path.stat().st_size,
        }

    def restore_backup(self, path: str) -> dict:
        """Restore data from a backup archive.

        Validates the archive, checks for path traversal, and extracts to the data directory.
        """
        validation = self.validate_backup(path)
        if not validation["valid"]:
            raise ValueError("Backup archive does not contain a database file")

        backup_path = Path(path)
        data_dir = Path("data")

        with tarfile.open(str(backup_path), "r:gz") as tar:
            # Security: check for path traversal attacks
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(
                        f"Backup contains unsafe path: {member.name}"
                    )

            # Extract database file
            for member in tar.getmembers():
                if member.name == "ulfweb.db":
                    # Extract DB to the configured path
                    with tar.extractfile(member) as src:
                        db_dest = Path(settings.database.path)
                        db_dest.parent.mkdir(parents=True, exist_ok=True)
                        with open(db_dest, "wb") as dst:
                            dst.write(src.read())
                elif member.name.startswith("data/"):
                    # Extract to the data directory
                    tar.extract(member, path=".")
                else:
                    # Top-level files get placed in data/
                    tar.extract(member, path=str(data_dir))

        logger.info("Backup restored from %s", backup_path)
        return {
            "restored": True,
            "filename": backup_path.name,
            "contents": validation["contents"],
        }

    def rotate_daily_backups(self, keep: int = 7) -> list[str]:
        """Keep the newest `keep` backups in the default directory, delete older ones."""
        DEFAULT_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backups = self.list_backups()
        deleted = []

        if len(backups) > keep:
            for backup in backups[keep:]:
                try:
                    os.unlink(backup["path"])
                    deleted.append(backup["filename"])
                    logger.info("Rotated old backup: %s", backup["filename"])
                except OSError as e:
                    logger.warning("Failed to delete old backup %s: %s", backup["filename"], e)

        return deleted

    def delete_backup(self, path: str) -> bool:
        """Delete a specific backup file."""
        backup_path = Path(path)
        if not backup_path.exists():
            return False
        if not backup_path.name.startswith(BACKUP_PREFIX):
            raise ValueError("Not a valid backup file")
        os.unlink(backup_path)
        logger.info("Deleted backup: %s", backup_path)
        return True

    def _today_backup_exists(self) -> bool:
        """Check if a backup for today already exists in the default directory."""
        today = date.today().strftime("%Y-%m-%d")
        if not DEFAULT_BACKUP_DIR.exists():
            return False
        for f in DEFAULT_BACKUP_DIR.glob(f"{BACKUP_PREFIX}{today}-*.tar.gz"):
            return True
        return False

    async def _scheduler_loop(self) -> None:
        """Background loop: check every 60s if today's backup exists."""
        while self._running:
            try:
                if not self._today_backup_exists():
                    logger.info("Scheduled daily backup starting...")
                    self.create_backup()
                    self.rotate_daily_backups()
                    logger.info("Scheduled daily backup completed")
            except Exception as e:
                self.last_error = str(e)
                self.last_failure_time = datetime.now().isoformat()
                logger.error("Scheduled backup failed: %s", e)

            await asyncio.sleep(60)

    def start_scheduler(self) -> None:
        """Start the background backup scheduler."""
        if self._scheduler_task is not None:
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Backup scheduler started")

    def stop_scheduler(self) -> None:
        """Stop the background backup scheduler."""
        self._running = False
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            self._scheduler_task = None
            logger.info("Backup scheduler stopped")


# Singleton instance
backup_service = BackupService()
