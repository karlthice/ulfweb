"""System resource information (RAM, VRAM, per-process memory)."""

import glob
import os


def get_system_ram() -> dict:
    """Read /proc/meminfo for system RAM stats.

    Returns dict with total, used, available in bytes.
    """
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemFree:", "MemAvailable:"):
                    # Values in /proc/meminfo are in kB
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


def get_gpu_vram() -> dict | None:
    """Read AMD GPU VRAM via /sys/class/drm.

    Returns dict with total, used, free in bytes, or None if no GPU found.
    """
    try:
        total_files = sorted(glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"))
        if not total_files:
            return None

        # Use the first GPU found
        base = os.path.dirname(total_files[0])

        with open(os.path.join(base, "mem_info_vram_total")) as f:
            total = int(f.read().strip())
        with open(os.path.join(base, "mem_info_vram_used")) as f:
            used = int(f.read().strip())

        return {
            "total": total,
            "used": used,
            "free": total - used,
        }
    except Exception:
        return None


def get_process_memory(pid: int) -> dict | None:
    """Get RAM and VRAM usage for a specific process.

    Reads VmRSS from /proc/{pid}/status for RAM.
    Scans /proc/{pid}/fdinfo/* for drm-total-vram and drm-total-gtt (AMD GPU).

    Returns dict with ram_bytes, vram_bytes, gtt_bytes, or None if process not found.
    """
    try:
        # Read RSS from /proc/{pid}/status
        ram_bytes = 0
        status_path = f"/proc/{pid}/status"
        with open(status_path) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    ram_bytes = int(parts[1]) * 1024  # kB -> bytes
                    break

        # Read per-process GPU memory from fdinfo
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
                                # Value is in KiB
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

        # Convert KiB to bytes for GPU values
        vram_bytes *= 1024
        gtt_bytes *= 1024

        return {
            "ram_bytes": ram_bytes,
            "vram_bytes": vram_bytes,
            "gtt_bytes": gtt_bytes,
        }
    except (FileNotFoundError, ProcessLookupError):
        return None
