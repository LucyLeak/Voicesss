from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RocmStatus:
    hipcc: str | None
    hip_runtime_dll: str | None
    hip_runtime_error: str | None
    hip_runtime_version: int | None
    hip_driver_version: int | None
    hip_device_count: int | None
    ctranslate2_version: str | None
    ctranslate2_rocm_supported: bool
    ctranslate2_rocm_error: str | None

    @property
    def hip_runtime_available(self) -> bool:
        return self.hip_runtime_dll is not None and self.hip_runtime_error is None


def _path_entries() -> list[Path]:
    entries: list[Path] = []
    env_names = ("HIP_PATH", "HIP_PATH_71", "HIP_PATH_64", "ROCM_PATH")
    for name in env_names:
        value = os.getenv(name)
        if value:
            entries.append(Path(value) / "bin")

    for item in os.getenv("PATH", "").split(os.pathsep):
        if item:
            entries.append(Path(item))

    entries.extend(
        [
            Path(r"C:\Program Files\AMD\ROCm\7.1\bin"),
            Path(r"C:\Program Files\AMD\ROCm\6.4\bin"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for entry in entries:
        key = str(entry).casefold()
        if key not in seen:
            unique.append(entry)
            seen.add(key)
    return unique


def _find_hip_runtime_dll() -> Path | None:
    dll_names = ("amdhip64_7.dll", "amdhip64_6.dll", "amdhip64.dll")
    for directory in _path_entries():
        for dll_name in dll_names:
            candidate = directory / dll_name
            if candidate.exists():
                return candidate
    return None


def _query_hip_runtime(dll_path: Path | None) -> tuple[str | None, int | None, int | None, int | None]:
    if dll_path is None:
        return "amdhip64 runtime DLL nao encontrada.", None, None, None

    try:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll_path.parent))
        dll = ctypes.CDLL(str(dll_path))
        count = ctypes.c_int(-1)
        runtime_version = ctypes.c_int(-1)
        driver_version = ctypes.c_int(-1)

        count_error = dll.hipGetDeviceCount(ctypes.byref(count))
        runtime_error = dll.hipRuntimeGetVersion(ctypes.byref(runtime_version))
        driver_error = dll.hipDriverGetVersion(ctypes.byref(driver_version))
    except Exception as exc:
        return str(exc), None, None, None

    if count_error != 0:
        return f"hipGetDeviceCount retornou erro {count_error}.", None, None, None

    return (
        None,
        runtime_version.value if runtime_error == 0 else None,
        driver_version.value if driver_error == 0 else None,
        count.value,
    )


def _query_ctranslate2_rocm() -> tuple[str | None, bool, str | None]:
    try:
        import ctranslate2
    except ImportError as exc:
        return None, False, f"CTranslate2 nao instalado: {exc}"

    for device in ("hip", "rocm"):
        try:
            ctranslate2.get_supported_compute_types(device)
            return ctranslate2.__version__, True, None
        except Exception as exc:
            last_error = f"{device}: {type(exc).__name__}: {exc}"

    return ctranslate2.__version__, False, last_error


def check_rocm() -> RocmStatus:
    hip_runtime_dll = _find_hip_runtime_dll()
    runtime_error, runtime_version, driver_version, device_count = _query_hip_runtime(hip_runtime_dll)
    ctranslate2_version, ctranslate2_rocm_supported, ctranslate2_rocm_error = _query_ctranslate2_rocm()

    return RocmStatus(
        hipcc=shutil.which("hipcc"),
        hip_runtime_dll=str(hip_runtime_dll) if hip_runtime_dll else None,
        hip_runtime_error=runtime_error,
        hip_runtime_version=runtime_version,
        hip_driver_version=driver_version,
        hip_device_count=device_count,
        ctranslate2_version=ctranslate2_version,
        ctranslate2_rocm_supported=ctranslate2_rocm_supported,
        ctranslate2_rocm_error=ctranslate2_rocm_error,
    )
