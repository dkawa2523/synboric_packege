#!/usr/bin/env python3
"""Download three UCI datasets and freeze numeric tables and group splits.

Python 3.11+. Concrete only: pandas and xlrd. No search engine or ClearML.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
from urllib.request import urlopen
import zipfile


SOURCES = {
    "yacht": {
        "id": 243, "slug": "yacht+hydrodynamics", "member": "yacht_hydrodynamics.data",
        "rows": 308,
        "columns": ["buoyancy_position", "prismatic_coefficient", "length_displacement_ratio",
                    "beam_draught_ratio", "length_beam_ratio", "froude", "resistance"],
        "units": ["1"] * 7, "group_indices": [0, 1, 2, 3, 4],
        "doi": "10.24432/C5XG7R",
    },
    "airfoil": {
        "id": 291, "slug": "airfoil+self+noise", "member": "airfoil_self_noise.dat",
        "rows": 1503,
        "columns": ["frequency", "attack_angle", "chord", "velocity", "displacement_thickness", "sound_level"],
        "units": ["Hz", "deg", "m", "m/s", "m", "dB"], "group_indices": [1, 2, 3, 4],
        "doi": "10.24432/C5VW2C",
    },
    "concrete": {
        "id": 165, "slug": "concrete+compressive+strength", "member": "Concrete_Data.xls",
        "rows": 1030,
        "columns": ["cement", "slag", "fly_ash", "water", "superplasticizer",
                    "coarse_aggregate", "fine_aggregate", "age", "strength"],
        "units": ["kg/m^3"] * 7 + ["day", "MPa"], "group_indices": list(range(7)),
        "doi": "10.24432/C5PK67",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def fetch_archive(folder: Path, url: str, offline: bool) -> bytes:
    archive = folder / "source.zip"
    checksum = folder / "source.sha256"
    if archive.exists():
        data = archive.read_bytes()
        if not checksum.exists() or checksum.read_text().strip() != sha256(data):
            raise ValueError(f"Cached source checksum mismatch: {archive}")
        return data
    if offline:
        raise FileNotFoundError(f"Offline source is missing: {archive}")
    with urlopen(url, timeout=45) as response:
        data = response.read(10_000_001)
    if len(data) > 10_000_000:
        raise ValueError("Unexpected archive size")
    # Check before keeping bytes. Never extract the archive to arbitrary paths.
    with zipfile.ZipFile(io.BytesIO(data)):
        pass
    archive.write_bytes(data)
    checksum.write_text(sha256(data) + "\n", encoding="ascii")
    return data


def read_rows(name: str, spec: dict, archive: bytes) -> list[list[float]]:
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        matches = [p for p in zipped.namelist() if Path(p).name == spec["member"]]
        if len(matches) != 1:
            raise ValueError(f"Expected one {spec['member']}, got {matches}")
        raw = zipped.read(matches[0])
    if name == "concrete":
        import pandas as pd
        rows = pd.read_excel(io.BytesIO(raw), engine="xlrd").to_numpy(dtype=float).tolist()
    else:
        rows = [[float(v) for v in line.split()] for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    if len(rows) != spec["rows"]:
        raise ValueError(f"Unexpected row count for {name}: {len(rows)}")
    if any(len(row) != len(spec["columns"]) or not all(math.isfinite(v) for v in row) for row in rows):
        raise ValueError(f"Invalid numeric table: {name}")
    return rows


def group_id(row: list[float], indices: list[int]) -> str:
    # Keep source numeric precision; do not round near-but-distinct designs together.
    key = json.dumps([row[i] for i in indices], separators=(",", ":"))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def prepare(name: str, root: Path, seed: int, offline: bool) -> dict:
    spec = SOURCES[name]
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    url = f"https://archive.ics.uci.edu/static/public/{spec['id']}/{spec['slug']}.zip"
    archive = fetch_archive(folder, url, offline)
    rows = read_rows(name, spec, archive)
    groups = [group_id(row, spec["group_indices"]) for row in rows]
    unique = sorted(set(groups))
    random.Random(seed).shuffle(unique)
    final_n = max(1, math.ceil(0.2 * len(unique)))
    selection_n = max(1, math.ceil(0.2 * (len(unique) - final_n)))
    if final_n + selection_n >= len(unique):
        raise ValueError("Not enough groups for three partitions")
    membership = {g: ("final" if i < final_n else "selection" if i < final_n + selection_n else "train")
                  for i, g in enumerate(unique)}
    by_split = {key: [] for key in ["train", "selection", "final"]}
    split_rows = []
    table = []
    for index, (row, group) in enumerate(zip(rows, groups)):
        sample = f"{name}-{index:05d}"
        split = membership[group]
        table.append([sample, group, *row])
        split_rows.append([sample, split])
        by_split[split].append(row)
    write_csv(folder / "table.csv", ["sample_id", "group_id", *spec["columns"]], table)
    write_csv(folder / "split.csv", ["sample_id", "partition"], split_rows)
    train_mean = sum(row[-1] for row in by_split["train"]) / len(by_split["train"])
    baseline = {}
    for split, values in by_split.items():
        baseline[split] = {
            "n_rows": len(values),
            "n_groups": sum(v == split for v in membership.values()),
        }
        # Final model metrics belong to finalization after model selection.
        if split != "final":
            baseline[split]["mean_predictor_rmse"] = math.sqrt(
                sum((r[-1] - train_mean) ** 2 for r in values) / len(values)
            )
    meta = {
        "dataset": name, "uci_id": spec["id"], "doi": spec["doi"], "license": "CC-BY-4.0",
        "source_url": url, "source_sha256": sha256(archive),
        "table_sha256": sha256((folder / "table.csv").read_bytes()),
        "split_sha256": sha256((folder / "split.csv").read_bytes()),
        "seed": seed, "target": spec["columns"][-1], "features": spec["columns"][:-1],
        "units": dict(zip(spec["columns"], spec["units"])),
        "group_features": [spec["columns"][i] for i in spec["group_indices"]],
        "group_definition": "Derived exact feature tuple; not an original experiment identifier",
        "rows": len(rows), "groups": len(unique),
        "exact_duplicate_rows": len(rows) - len(set(tuple(row) for row in rows)),
        "split_rule": "Group shuffle seed; ceil(0.2*G) final, ceil(0.2*remaining_G) selection",
        "partitions": baseline, "truth_formula": None,
        "pretraining_overlap": "unknown; public dataset is not guaranteed unseen",
    }
    write_json(folder / "metadata.json", meta)
    return {"dataset": name, "rows": len(rows), "groups": len(unique), "partitions": baseline}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--dataset", choices=["all", *SOURCES], default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    names = list(SOURCES) if args.dataset == "all" else [args.dataset]
    for name in names:
        print(json.dumps(prepare(name, args.out, args.seed, args.offline), ensure_ascii=False))


if __name__ == "__main__":
    main()
