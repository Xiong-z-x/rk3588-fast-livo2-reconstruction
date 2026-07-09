from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


PCD_TYPES = {
    ("F", 4): "<f4",
    ("F", 8): "<f8",
    ("I", 1): "<i1",
    ("I", 2): "<i2",
    ("I", 4): "<i4",
    ("I", 8): "<i8",
    ("U", 1): "<u1",
    ("U", 2): "<u2",
    ("U", 4): "<u4",
    ("U", 8): "<u8",
}


@dataclass(frozen=True)
class PcdHeader:
    path: Path
    fields: tuple[str, ...]
    sizes: tuple[int, ...]
    types: tuple[str, ...]
    counts: tuple[int, ...]
    points: int
    width: int
    height: int
    data: str
    data_offset: int
    dtype: np.dtype


def read_pcd_header(path: str | Path) -> PcdHeader:
    pcd_path = Path(path)
    values: dict[str, list[str]] = {}
    offset = 0
    with pcd_path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError("PCD header is missing DATA")
            offset += len(line)
            decoded = line.decode("ascii", errors="replace").strip()
            if not decoded or decoded.startswith("#"):
                continue
            parts = decoded.split()
            values[parts[0].upper()] = parts[1:]
            if parts[0].upper() == "DATA":
                break

    fields = tuple(values.get("FIELDS", ()))
    if not {"x", "y", "z"}.issubset(fields):
        raise ValueError("PCD must contain x, y and z fields")
    sizes = tuple(int(v) for v in values.get("SIZE", ()))
    types = tuple(values.get("TYPE", ()))
    counts = tuple(int(v) for v in values.get("COUNT", ["1"] * len(fields)))
    if not (len(fields) == len(sizes) == len(types) == len(counts)):
        raise ValueError("PCD FIELDS/SIZE/TYPE/COUNT length mismatch")

    dtype_fields: list[tuple] = []
    for field, size, kind, count in zip(fields, sizes, types, counts):
        fmt = PCD_TYPES.get((kind, size))
        if fmt is None:
            raise ValueError(f"Unsupported PCD field type: {field} {kind}{size}")
        dtype_fields.append((field, fmt) if count == 1 else (field, fmt, (count,)))

    width = int(values.get("WIDTH", ["0"])[0])
    height = int(values.get("HEIGHT", ["1"])[0])
    points = int(values.get("POINTS", [str(width * height)])[0])
    data = values["DATA"][0].lower()
    if data not in {"binary", "ascii"}:
        raise ValueError(f"Unsupported PCD DATA mode: {data}")

    return PcdHeader(
        path=pcd_path,
        fields=fields,
        sizes=sizes,
        types=types,
        counts=counts,
        points=points,
        width=width,
        height=height,
        data=data,
        data_offset=offset,
        dtype=np.dtype(dtype_fields),
    )


def _header_line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for line in handle:
            count += 1
            if line.lstrip().upper().startswith(b"DATA"):
                break
    return count


def read_structured_points(path: str | Path) -> tuple[PcdHeader, np.ndarray]:
    header = read_pcd_header(path)
    if header.data == "binary":
        data = np.memmap(
            header.path,
            dtype=header.dtype,
            mode="r",
            offset=header.data_offset,
            shape=(header.points,),
        )
        return header, data

    rows = np.loadtxt(header.path, skiprows=_header_line_count(header.path))
    if rows.ndim == 1:
        rows = rows.reshape(1, -1)
    structured = np.empty(rows.shape[0], dtype=header.dtype)
    cursor = 0
    for field, count in zip(header.fields, header.counts):
        if count == 1:
            structured[field] = rows[:, cursor]
        else:
            structured[field] = rows[:, cursor : cursor + count]
        cursor += count
    return header, structured


def xyz_matrix(data: np.ndarray) -> np.ndarray:
    xyz = np.column_stack(
        (
            np.asarray(data["x"], dtype=np.float32),
            np.asarray(data["y"], dtype=np.float32),
            np.asarray(data["z"], dtype=np.float32),
        )
    )
    return xyz[np.isfinite(xyz).all(axis=1)]


def load_xyz(path: str | Path, limit: int | None = None) -> np.ndarray:
    header, data = read_structured_points(path)
    if limit and header.points > limit:
        step = max(1, math.ceil(header.points / limit))
        data = data[::step]
    return xyz_matrix(data)


def crop_roi(points: np.ndarray, bbox_min: tuple[float, float, float], bbox_max: tuple[float, float, float]) -> np.ndarray:
    lo = np.asarray(bbox_min, dtype=np.float32)
    hi = np.asarray(bbox_max, dtype=np.float32)
    mask = np.all((points >= lo) & (points <= hi), axis=1)
    roi = points[mask]
    if len(roi) < 32:
        raise ValueError("ROI contains too few points for AI inference")
    return roi.astype(np.float32, copy=False)
