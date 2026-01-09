"""
Iris GPU Detection

Detects GPU information for node capability reporting.
Supports NVIDIA (via pynvml), Apple Silicon, and fallback defaults.
"""

import platform
import subprocess
from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger()


@dataclass
class GPUInfo:
    """GPU information container."""
    name: str
    vram_total_gb: float
    vram_free_gb: float
    vendor: str  # "nvidia", "apple", "amd", "unknown"


class GPUDetector:
    """
    Detects GPU information across different platforms.

    Priority:
    1. NVIDIA GPUs via pynvml
    2. Apple Silicon via system_profiler
    3. Environment variable overrides
    4. Default fallback values
    """

    @staticmethod
    def detect() -> GPUInfo:
        """
        Detect GPU and return information.

        Returns:
            GPUInfo with detected or default values
        """
        # Try NVIDIA first
        nvidia_info = GPUDetector._detect_nvidia()
        if nvidia_info:
            logger.info(
                "gpu_detected",
                vendor="nvidia",
                name=nvidia_info.name,
                vram_gb=nvidia_info.vram_total_gb
            )
            return nvidia_info

        # Try Apple Silicon
        apple_info = GPUDetector._detect_apple_silicon()
        if apple_info:
            logger.info(
                "gpu_detected",
                vendor="apple",
                name=apple_info.name,
                vram_gb=apple_info.vram_total_gb
            )
            return apple_info

        # Try AMD
        amd_info = GPUDetector._detect_amd()
        if amd_info:
            logger.info(
                "gpu_detected",
                vendor="amd",
                name=amd_info.name,
                vram_gb=amd_info.vram_total_gb
            )
            return amd_info

        # Fallback
        logger.warning("gpu_not_detected", using="defaults")
        return GPUInfo(
            name="Unknown GPU",
            vram_total_gb=8.0,
            vram_free_gb=4.0,
            vendor="unknown"
        )

    @staticmethod
    def _detect_nvidia() -> Optional[GPUInfo]:
        """Detect NVIDIA GPU using pynvml."""
        try:
            import pynvml
            pynvml.nvmlInit()

            # Get first GPU (index 0)
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)

            # Handle bytes vs string (varies by pynvml version)
            if isinstance(name, bytes):
                name = name.decode('utf-8')

            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_total = mem_info.total / (1024 ** 3)  # Convert to GB
            vram_free = mem_info.free / (1024 ** 3)

            pynvml.nvmlShutdown()

            return GPUInfo(
                name=name,
                vram_total_gb=round(vram_total, 2),
                vram_free_gb=round(vram_free, 2),
                vendor="nvidia"
            )
        except ImportError:
            logger.debug("pynvml_not_installed")
            return None
        except Exception as e:
            logger.debug("nvidia_detection_failed", error=str(e))
            return None

    @staticmethod
    def _detect_apple_silicon() -> Optional[GPUInfo]:
        """Detect Apple Silicon GPU using system_profiler."""
        if platform.system() != "Darwin":
            return None

        try:
            # Check if running on Apple Silicon
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5
            )
            cpu_brand = result.stdout.strip()

            if "Apple" not in cpu_brand:
                return None

            # Get chip name (M1, M2, M3, etc.)
            chip_name = "Apple Silicon"
            if "M1" in cpu_brand:
                chip_name = "Apple M1"
            elif "M2" in cpu_brand:
                chip_name = "Apple M2"
            elif "M3" in cpu_brand:
                chip_name = "Apple M3"
            elif "M4" in cpu_brand:
                chip_name = "Apple M4"

            # Get unified memory (shared between CPU and GPU)
            mem_result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5
            )
            total_mem_bytes = int(mem_result.stdout.strip())
            total_mem_gb = total_mem_bytes / (1024 ** 3)

            # Apple Silicon shares memory - estimate GPU portion
            # Typically 50-75% can be used by GPU
            gpu_mem_gb = total_mem_gb * 0.7

            return GPUInfo(
                name=chip_name,
                vram_total_gb=round(gpu_mem_gb, 2),
                vram_free_gb=round(gpu_mem_gb * 0.5, 2),  # Estimate 50% free
                vendor="apple"
            )
        except Exception as e:
            logger.debug("apple_detection_failed", error=str(e))
            return None

    @staticmethod
    def _detect_amd() -> Optional[GPUInfo]:
        """
        Detect AMD GPU.

        Strategy:
        1. Windows: Use WMI (Win32_VideoController)
        2. Linux: Use rocm-smi
        """
        system = platform.system()

        if system == "Windows":
            return GPUDetector._detect_amd_windows()
        else:
            return GPUDetector._detect_amd_linux()

    @staticmethod
    def _detect_amd_windows() -> Optional[GPUInfo]:
        """Detect AMD GPU on Windows using WMI."""
        try:
            # Try using WMI module first
            try:
                import wmi
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    gpu_name = gpu.Name or "Unknown GPU"
                    # Check if it's an AMD GPU
                    if any(x in gpu_name.upper() for x in ["AMD", "RADEON", "ATI"]):
                        # AdapterRAM is in bytes, but can be None or incorrect for >4GB
                        vram_bytes = gpu.AdapterRAM
                        if vram_bytes and vram_bytes > 0:
                            vram_gb = vram_bytes / (1024 ** 3)
                            # WMI can report incorrect values for >4GB due to 32-bit limit
                            if vram_gb < 1:
                                vram_gb = GPUDetector._estimate_amd_vram(gpu_name)
                        else:
                            vram_gb = GPUDetector._estimate_amd_vram(gpu_name)

                        logger.info("amd_gpu_detected_wmi", name=gpu_name, vram_gb=vram_gb)
                        return GPUInfo(
                            name=gpu_name,
                            vram_total_gb=round(vram_gb, 2),
                            vram_free_gb=round(vram_gb * 0.8, 2),
                            vendor="amd"
                        )
            except ImportError:
                logger.debug("wmi_module_not_available")

            # Fallback: Use wmic command directly
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name,AdapterRAM", "/format:csv"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True  # Required for wmic on some Windows versions
            )

            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                for line in lines[1:]:  # Skip header
                    parts = line.split(',')
                    if len(parts) >= 3:
                        adapter_ram = parts[1] if parts[1] else "0"
                        gpu_name = parts[2] if len(parts) > 2 else "Unknown"

                        if any(x in gpu_name.upper() for x in ["AMD", "RADEON", "ATI"]):
                            try:
                                vram_bytes = int(adapter_ram) if adapter_ram.isdigit() else 0
                                vram_gb = vram_bytes / (1024 ** 3) if vram_bytes > 0 else 8.0
                                if vram_gb < 1:
                                    vram_gb = GPUDetector._estimate_amd_vram(gpu_name)
                            except:
                                vram_gb = GPUDetector._estimate_amd_vram(gpu_name)

                            logger.info("amd_gpu_detected_wmic", name=gpu_name, vram_gb=vram_gb)
                            return GPUInfo(
                                name=gpu_name,
                                vram_total_gb=round(vram_gb, 2),
                                vram_free_gb=round(vram_gb * 0.8, 2),
                                vendor="amd"
                            )

            return None

        except Exception as e:
            logger.debug("amd_windows_detection_failed", error=str(e))
            return None

    @staticmethod
    def _estimate_amd_vram(gpu_name: str) -> float:
        """Estimate VRAM based on GPU model name."""
        name_upper = gpu_name.upper()

        # RX 7000 series
        if "7900" in name_upper:
            return 24.0 if "XTX" in name_upper else 20.0
        if "7800" in name_upper:
            return 16.0
        if "7700" in name_upper:
            return 12.0
        if "7600" in name_upper:
            return 8.0

        # RX 6000 series
        if "6950" in name_upper or "6900" in name_upper:
            return 16.0
        if "6800" in name_upper:
            return 16.0
        if "6750" in name_upper or "6700" in name_upper:
            return 12.0
        if "6650" in name_upper or "6600" in name_upper:
            return 8.0
        if "6500" in name_upper:
            return 4.0

        # RX 5000 series
        if "5700" in name_upper:
            return 8.0
        if "5600" in name_upper:
            return 6.0
        if "5500" in name_upper:
            return 8.0 if "8G" in name_upper else 4.0

        # Default for unknown AMD GPUs
        return 8.0

    @staticmethod
    def _detect_amd_linux() -> Optional[GPUInfo]:
        """Detect AMD GPU on Linux using rocm-smi."""
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            # Parse rocm-smi output
            output = result.stdout
            lines = output.strip().split('\n')

            vram_total = 8.0
            vram_free = 4.0
            gpu_name = "AMD GPU"

            for line in lines:
                if "Total Memory" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if i < len(parts) and "MB" in parts[i]:
                            try:
                                vram_total = float(parts[i-1]) / 1024
                            except:
                                pass

            # Try to get GPU name
            name_result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if name_result.returncode == 0:
                for line in name_result.stdout.split('\n'):
                    if "Card" in line or "GPU" in line:
                        gpu_name = line.split(":")[-1].strip() if ":" in line else line.strip()
                        break

            return GPUInfo(
                name=gpu_name,
                vram_total_gb=round(vram_total, 2),
                vram_free_gb=round(vram_free, 2),
                vendor="amd"
            )
        except FileNotFoundError:
            logger.debug("rocm_smi_not_found")
            return None
        except Exception as e:
            logger.debug("amd_linux_detection_failed", error=str(e))
            return None

    @staticmethod
    def get_current_vram_free() -> float:
        """
        Get current free VRAM (for real-time updates).

        Returns:
            Free VRAM in GB, or 0.0 if unknown
        """
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_free = mem_info.free / (1024 ** 3)
            pynvml.nvmlShutdown()
            return round(vram_free, 2)
        except:
            return 0.0


# Convenience function
def detect_gpu() -> GPUInfo:
    """Detect GPU information."""
    return GPUDetector.detect()
