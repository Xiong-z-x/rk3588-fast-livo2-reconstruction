from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


try:
    from rknnlite.api import RKNNLite
except Exception:  # pragma: no cover - only available on RK3588 runtime images
    RKNNLite = None  # type: ignore[assignment]


CORE_MASKS = {
    "core0": 1,
    "core1": 2,
    "core2": 4,
    "core0_1": 3,
    "core1_2": 6,
    "core0_1_2": 7,
}


@dataclass(frozen=True)
class RknnTensorInfo:
    index: int
    shape: tuple[int, ...]
    dtype: str


class RknnRuntimeError(RuntimeError):
    pass


class RknnRuntime:
    def __init__(self, model_path: str | Path, core_mask: str = "core0_1_2") -> None:
        self.model_path = Path(model_path)
        self.core_mask = core_mask
        self._runtime = None

    def __enter__(self) -> "RknnRuntime":
        self.load()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def load(self) -> None:
        if self._runtime is not None:
            return
        if RKNNLite is None:
            raise RknnRuntimeError("rknnlite.api.RKNNLite is not installed in this environment")
        if not self.model_path.exists():
            raise FileNotFoundError(f"RKNN model not found: {self.model_path}")
        if self.core_mask not in CORE_MASKS:
            raise ValueError(f"Unsupported RKNN core mask: {self.core_mask}")

        runtime = RKNNLite()
        ret = runtime.load_rknn(str(self.model_path))
        if ret != 0:
            raise RknnRuntimeError(f"RKNN load_rknn failed with code {ret}: {self.model_path}")

        ret = runtime.init_runtime(core_mask=CORE_MASKS[self.core_mask])
        if ret != 0:
            runtime.release()
            raise RknnRuntimeError(f"RKNN init_runtime failed with code {ret}")

        self._runtime = runtime

    def infer(self, inputs: Iterable[np.ndarray]) -> list[np.ndarray]:
        if self._runtime is None:
            self.load()
        prepared = [np.ascontiguousarray(item) for item in inputs]
        outputs = self._runtime.inference(inputs=prepared)
        if outputs is None:
            raise RknnRuntimeError("RKNN inference returned no outputs")
        return [np.asarray(output) for output in outputs]

    def release(self) -> None:
        if self._runtime is not None:
            self._runtime.release()
            self._runtime = None

    def close(self) -> None:
        self.release()
