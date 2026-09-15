from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


class HardwareError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareProfile:
    has_gpu: bool
    gpu_name: str
    vram_gb: float
    ram_gb: float

    @property
    def usable_gb(self) -> float:
        """VRAM if a usable dedicated GPU was found, else system RAM for CPU inference."""
        return self.vram_gb if self.has_gpu else self.ram_gb


@dataclass(frozen=True)
class ModelRecommendation:
    model: str
    reason: str


def recommend_model(profile: HardwareProfile) -> ModelRecommendation:
    """Pick a vision-capable Ollama model sized for the detected hardware."""
    budget = profile.usable_gb
    if not profile.has_gpu:
        if budget >= 16:
            return ModelRecommendation(
                "qwen2.5vl:7b",
                f"No dedicated GPU detected, but {budget:.0f} GB of system RAM can run a "
                "7B vision model on CPU (expect it to be slow).",
            )
        return ModelRecommendation(
            "qwen2.5vl:3b",
            f"No dedicated GPU detected; with {budget:.0f} GB of system RAM, a 3B vision "
            "model is the most that will run reasonably on CPU.",
        )
    if budget >= 18:
        return ModelRecommendation(
            "mistral-small3.1:24b",
            f"{profile.gpu_name} has {budget:.0f} GB VRAM, enough for the 24B vision model.",
        )
    if budget >= 9:
        return ModelRecommendation(
            "gemma3:12b",
            f"{profile.gpu_name} has {budget:.0f} GB VRAM, a good fit for a 12B vision model.",
        )
    if budget >= 6:
        return ModelRecommendation(
            "qwen2.5vl:7b",
            f"{profile.gpu_name} has {budget:.0f} GB VRAM, a good fit for the 7B vision model.",
        )
    return ModelRecommendation(
        "qwen2.5vl:3b",
        f"{profile.gpu_name} has only {budget:.0f} GB VRAM; a 3B vision model is the safest fit.",
    )


def _powershell(command: str, timeout: int = 15) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if result.returncode != 0:
        raise HardwareError(f"PowerShell command failed: {result.stderr.strip() or 'unknown error'}")
    return result.stdout


def _system_ram_gb() -> float:
    if sys.platform != "win32":
        raise HardwareError("Automatic hardware detection is only available on Windows")
    output = _powershell("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
    try:
        return float(output.strip()) / (1024**3)
    except ValueError as exc:
        raise HardwareError("Could not read system RAM") from exc


def _nvidia_smi_vram_gb() -> tuple[str, float] | None:
    """Prefer nvidia-smi for VRAM: Windows' WMI AdapterRAM is frequently misreported
    (often capped near 4 GB) on modern NVIDIA drivers."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    first_line = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first_line.split(",")]
    if len(parts) != 2:
        return None
    name, mib_text = parts
    try:
        return name, float(mib_text) / 1024
    except ValueError:
        return None


def _gpu_info() -> tuple[str, float]:
    nvidia = _nvidia_smi_vram_gb()
    if nvidia:
        return nvidia
    if sys.platform != "win32":
        return "", 0.0
    output = _powershell(
        "$gpu = Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending "
        "| Select-Object -First 1; Write-Output $gpu.Name; Write-Output $gpu.AdapterRAM"
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "", 0.0
    name = lines[0]
    vram_bytes = 0.0
    if len(lines) > 1:
        try:
            vram_bytes = float(lines[1])
        except ValueError:
            vram_bytes = 0.0
    return name, vram_bytes / (1024**3)


def detect_hardware() -> HardwareProfile:
    ram_gb = _system_ram_gb()
    gpu_name, vram_gb = _gpu_info()
    # Treat a GPU with well under 1 GB reported VRAM as "no usable dedicated GPU" --
    # this is typically a misreported/disabled integrated adapter rather than a real one.
    has_gpu = bool(gpu_name) and vram_gb >= 1.0
    return HardwareProfile(has_gpu=has_gpu, gpu_name=gpu_name, vram_gb=vram_gb, ram_gb=ram_gb)
