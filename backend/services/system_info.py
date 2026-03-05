"""System resource information (RAM, VRAM, per-process memory)."""

import glob
import os
import platform
import shutil
import subprocess

_IS_MACOS = platform.system() == "Darwin"


def _get_system_ram_linux() -> dict:
    """Read /proc/meminfo for system RAM stats."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemFree:", "MemAvailable:"):
                    info[parts[0].rstrip(":")] = int(parts[1]) * 1024

        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        return {
            "total": total,
            "used": total - available,
            "available": available,
        }
    except Exception:
        return {"total": 0, "used": 0, "available": 0}


def _get_system_ram_macos() -> dict:
    """Read system RAM via sysctl and vm_stat on macOS."""
    try:
        # Total RAM
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5,
        )
        total = int(result.stdout.strip())

        # Parse vm_stat for page-level usage
        result = subprocess.run(
            ["vm_stat"],
            capture_output=True, text=True, timeout=5,
        )
        pages = {}
        page_size = 16384  # default
        for line in result.stdout.splitlines():
            if "page size of" in line:
                page_size = int(line.split()[-2])
            elif ":" in line:
                key, _, val = line.partition(":")
                val = val.strip().rstrip(".")
                if val.isdigit():
                    pages[key.strip()] = int(val)

        free_pages = pages.get("Pages free", 0)
        inactive_pages = pages.get("Pages inactive", 0)
        speculative_pages = pages.get("Pages speculative", 0)
        available = (free_pages + inactive_pages + speculative_pages) * page_size

        return {
            "total": total,
            "used": total - available,
            "available": available,
        }
    except Exception:
        return {"total": 0, "used": 0, "available": 0}


def get_system_ram() -> dict:
    """Get system RAM stats. Returns dict with total, used, available in bytes."""
    if _IS_MACOS:
        return _get_system_ram_macos()
    return _get_system_ram_linux()


def _get_gpu_vram_amd() -> dict | None:
    """Read AMD GPU VRAM via /sys/class/drm."""
    try:
        total_files = sorted(glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"))
        if not total_files:
            return None

        base = os.path.dirname(total_files[0])

        with open(os.path.join(base, "mem_info_vram_total")) as f:
            total = int(f.read().strip())
        with open(os.path.join(base, "mem_info_vram_used")) as f:
            used = int(f.read().strip())

        return {
            "total": total,
            "used": used,
            "free": total - used,
            "vendor": "amd",
        }
    except Exception:
        return None


def _get_gpu_vram_nvidia() -> dict | None:
    """Read NVIDIA GPU VRAM via nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        # Use first GPU; values are in MiB
        line = result.stdout.strip().splitlines()[0]
        total_mib, used_mib, free_mib = (int(v.strip()) for v in line.split(","))

        return {
            "total": total_mib * 1024 * 1024,
            "used": used_mib * 1024 * 1024,
            "free": free_mib * 1024 * 1024,
            "vendor": "nvidia",
        }
    except Exception:
        return None


def _get_gpu_vram_apple() -> dict | None:
    """Report Apple Silicon unified memory as GPU memory.

    Apple Silicon uses shared unified memory for both CPU and GPU (Metal).
    We report total system RAM as GPU capacity since Metal can use all of it.
    """
    if not _IS_MACOS:
        return None
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        total = int(result.stdout.strip())
        ram = get_system_ram()

        return {
            "total": total,
            "used": ram["used"],
            "free": ram["available"],
            "vendor": "apple",
        }
    except Exception:
        return None


def get_gpu_vram() -> dict | None:
    """Detect GPU VRAM (AMD, NVIDIA, or Apple Silicon).

    Returns dict with total, used, free in bytes, or None if no GPU found.
    """
    return _get_gpu_vram_amd() or _get_gpu_vram_nvidia() or _get_gpu_vram_apple()


def _get_process_vram_nvidia(pid: int) -> int:
    """Get VRAM usage for a specific process via nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return 0
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return 0

        for line in result.stdout.strip().splitlines():
            parts = line.split(",")
            if len(parts) == 2 and int(parts[0].strip()) == pid:
                return int(parts[1].strip()) * 1024 * 1024  # MiB -> bytes
        return 0
    except Exception:
        return 0


def _get_process_vram_amd(pid: int) -> tuple[int, int]:
    """Get VRAM and GTT usage for a specific process via /proc fdinfo (AMD).

    Returns (vram_bytes, gtt_bytes).
    """
    vram_bytes = 0
    gtt_bytes = 0
    fdinfo_dir = f"/proc/{pid}/fdinfo"
    try:
        for entry in os.listdir(fdinfo_dir):
            try:
                with open(os.path.join(fdinfo_dir, entry)) as f:
                    found_drm = False
                    for line in f:
                        if line.startswith("drm-total-vram:"):
                            val = int(line.split()[1])
                            if val > vram_bytes:
                                vram_bytes = val
                            found_drm = True
                        elif line.startswith("drm-total-gtt:"):
                            val = int(line.split()[1])
                            if val > gtt_bytes:
                                gtt_bytes = val
                            found_drm = True
                        elif found_drm and not line.startswith("drm-"):
                            break
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    return vram_bytes * 1024, gtt_bytes * 1024


def _get_process_ram_macos(pid: int) -> int:
    """Get RSS for a process on macOS via ps."""
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip()) * 1024  # kB -> bytes
    except Exception:
        return 0


def get_process_memory(pid: int) -> dict | None:
    """Get RAM and VRAM usage for a specific process.

    Supports Linux (/proc), AMD (fdinfo), NVIDIA (nvidia-smi), and macOS (ps).

    Returns dict with ram_bytes, vram_bytes, gtt_bytes, or None if process not found.
    """
    try:
        if _IS_MACOS:
            ram_bytes = _get_process_ram_macos(pid)
            if ram_bytes == 0:
                return None
            # On Apple Silicon, Metal GPU memory is part of unified RAM.
            # Report process RSS as both RAM and VRAM usage.
            return {
                "ram_bytes": ram_bytes,
                "vram_bytes": ram_bytes,
                "gtt_bytes": 0,
            }

        # Linux: read RSS from /proc/{pid}/status
        ram_bytes = 0
        status_path = f"/proc/{pid}/status"
        with open(status_path) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    ram_bytes = int(parts[1]) * 1024
                    break

        # Try AMD first (no subprocess overhead), then NVIDIA
        vram_bytes, gtt_bytes = _get_process_vram_amd(pid)
        if vram_bytes == 0:
            vram_bytes = _get_process_vram_nvidia(pid)

        return {
            "ram_bytes": ram_bytes,
            "vram_bytes": vram_bytes,
            "gtt_bytes": gtt_bytes,
        }
    except (FileNotFoundError, ProcessLookupError):
        return None
