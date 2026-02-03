"""Process manager for llama.cpp servers."""

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from backend.config import settings

logger = logging.getLogger(__name__)


class LlamaManager:
    """Manages llama.cpp server processes."""

    def __init__(self):
        self.processes: dict[int, subprocess.Popen] = {}  # server_id -> process

    @property
    def _llama_server_path(self) -> str:
        """Get llama-server path from config or environment."""
        return os.environ.get("LLAMA_SERVER_PATH") or settings.models.llama_server

    def _extract_port(self, url: str) -> int | None:
        """Extract port from server URL."""
        try:
            parsed = urlparse(url)
            if parsed.port:
                return parsed.port
            # Default ports
            if parsed.scheme == "https":
                return 443
            return 80
        except Exception:
            return None

    def _find_mmproj_file(self, model_path: str) -> str | None:
        """Find a matching mmproj file for vision models.

        Only matches mmproj files that share a common base name with the model.
        For example, for 'Qwen3VL-32B-Instruct-Q4_K_M.gguf', would match
        'mmproj-Qwen3VL-32B-Instruct-F16.gguf' but not unrelated mmproj files.
        """
        if not model_path:
            return None

        model_dir = Path(model_path).parent
        model_name = Path(model_path).stem

        # Extract base model name (without quantization suffix like Q4_K_M)
        # Common patterns: ModelName-Size-Q4_K_M, ModelName-Q4_K_M
        base_name = model_name
        for suffix in ['-Q4_K_M', '-Q4_K_S', '-Q5_K_M', '-Q5_K_S', '-Q6_K', '-Q8_0', '-F16', '-F32']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break

        # Look for mmproj files that match this specific model
        for mmproj in model_dir.glob("*mmproj*.gguf"):
            mmproj_name = mmproj.stem.lower()
            # Check if the mmproj file name contains the base model name
            if base_name.lower() in mmproj_name or mmproj_name.replace('mmproj-', '').replace('-mmproj', '') in base_name.lower():
                return str(mmproj)

        return None

    async def start_server(
        self, server_id: int, model_path: str, url: str, parallel: int = 1, ctx_size: int = 32768
    ) -> bool:
        """Start a llama.cpp server process."""
        if not model_path:
            logger.warning(f"Server {server_id}: No model path configured")
            return False

        # Check if already running
        if server_id in self.processes:
            proc = self.processes[server_id]
            if proc.poll() is None:  # Process is still running
                logger.info(f"Server {server_id}: Already running (PID {proc.pid})")
                return True

        port = self._extract_port(url)
        if not port:
            logger.error(f"Server {server_id}: Could not extract port from URL {url}")
            return False

        # Build command
        cmd = [
            self._llama_server_path,
            "-m", model_path,
            "--port", str(port),
            "-np", str(parallel),
            "-c", str(ctx_size),
        ]

        # Check for vision model (mmproj file)
        mmproj = self._find_mmproj_file(model_path)
        if mmproj:
            cmd.extend(["--mmproj", mmproj])
            logger.info(f"Server {server_id}: Detected vision model, using mmproj: {mmproj}")

        logger.info(f"Server {server_id}: Starting llama-server with command: {' '.join(cmd)}")

        try:
            # Start process with output logged to file for debugging
            log_dir = Path("data/logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"llama-server-{server_id}.log"

            with open(log_file, "a") as f:
                f.write(f"\n--- Starting server {server_id} at {asyncio.get_event_loop().time()} ---\n")
                f.write(f"Command: {' '.join(cmd)}\n")

            log_handle = open(log_file, "a")
            proc = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,  # Detach from parent process group
            )
            self.processes[server_id] = proc
            self._log_handles = getattr(self, '_log_handles', {})
            self._log_handles[server_id] = log_handle

            # Wait briefly to check if process started successfully
            await asyncio.sleep(0.5)
            if proc.poll() is not None:
                logger.error(f"Server {server_id}: Process exited immediately with code {proc.returncode}")
                del self.processes[server_id]
                return False

            logger.info(f"Server {server_id}: Started successfully (PID {proc.pid})")
            return True

        except FileNotFoundError:
            logger.error(f"Server {server_id}: llama-server not found at {self._llama_server_path}")
            return False
        except Exception as e:
            logger.error(f"Server {server_id}: Failed to start: {e}")
            return False

    async def stop_server(self, server_id: int) -> bool:
        """Stop a llama.cpp server process."""
        if server_id not in self.processes:
            logger.info(f"Server {server_id}: No process tracked")
            return True

        proc = self.processes[server_id]

        if proc.poll() is not None:
            # Process already terminated
            logger.info(f"Server {server_id}: Process already terminated")
            del self.processes[server_id]
            return True

        try:
            logger.info(f"Server {server_id}: Terminating process (PID {proc.pid})")
            proc.terminate()

            # Wait for graceful shutdown
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"Server {server_id}: Process didn't terminate, killing...")
                proc.kill()
                proc.wait(timeout=2)

            del self.processes[server_id]
            logger.info(f"Server {server_id}: Stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Server {server_id}: Failed to stop: {e}")
            return False

    def get_status(self, server_id: int) -> bool:
        """Check if a server process is running."""
        if server_id not in self.processes:
            return False

        proc = self.processes[server_id]
        return proc.poll() is None

    async def restart_server(
        self, server_id: int, model_path: str, url: str, parallel: int = 1, ctx_size: int = 32768
    ) -> bool:
        """Restart a llama.cpp server process."""
        await self.stop_server(server_id)
        await asyncio.sleep(0.5)  # Brief delay before restart
        return await self.start_server(server_id, model_path, url, parallel, ctx_size)

    def cleanup(self):
        """Stop all managed processes (for shutdown)."""
        for server_id in list(self.processes.keys()):
            try:
                proc = self.processes[server_id]
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception as e:
                logger.error(f"Server {server_id}: Error during cleanup: {e}")

        self.processes.clear()


# Global instance
llama_manager = LlamaManager()
