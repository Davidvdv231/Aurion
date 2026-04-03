from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.ml.model import AnalogForecastModel


@dataclass(slots=True)
class ModelArtifact:
    name: str
    version: str
    path: Path
    metadata: dict[str, object]


class ModelRegistry:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, model: AnalogForecastModel, metadata: dict[str, object] | None = None) -> ModelArtifact:
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{uuid.uuid4().hex[:8]}"
        artifact_dir = self.root / model.model_name / version
        artifact_dir.mkdir(parents=True, exist_ok=False)

        state = model.to_state()
        array_state = {key: value for key, value in state.items() if isinstance(value, np.ndarray)}
        scalar_state = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in state.items()
            if key not in array_state
        }
        array_state_kwargs: dict[str, Any] = dict(array_state)
        np.savez_compressed(artifact_dir / "state.npz", **array_state_kwargs)

        meta = {
            "name": model.model_name,
            "version": version,
            "lookback": model.lookback,
            "horizon": model.horizon,
            "top_k": model.top_k,
            "feature_columns": list(model.feature_columns),
            "asset_type": model.asset_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state_meta": scalar_state,
        }
        if metadata:
            meta.update(metadata)

        (artifact_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        return ModelArtifact(name=model.model_name, version=version, path=artifact_dir, metadata=meta)

    def load_latest(self, name: str) -> AnalogForecastModel:
        versions_root = self.root / name
        if not versions_root.exists():
            raise FileNotFoundError(f"No artifacts found for model '{name}'.")

        candidates = sorted((path for path in versions_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
        if not candidates:
            raise FileNotFoundError(f"No artifact versions found for model '{name}'.")
        return self.load(candidates[0])

    def load(self, artifact_dir: Path | str) -> AnalogForecastModel:
        artifact_dir = Path(artifact_dir)
        metadata_path = artifact_dir / "metadata.json"
        state_path = artifact_dir / "state.npz"
        if not metadata_path.exists() or not state_path.exists():
            raise FileNotFoundError("Artifact directory is incomplete.")

        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        state_file = np.load(state_path, allow_pickle=True)
        state = dict(meta.get("state_meta", {}))
        if not state:
            state = {
                "lookback": meta["lookback"],
                "horizon": meta["horizon"],
                "top_k": meta["top_k"],
                "feature_columns": meta["feature_columns"],
                "model_name": meta["name"],
                "asset_type": meta["asset_type"],
            }
        for key in state_file.files:
            state[key] = state_file[key]
        return AnalogForecastModel.from_state(state)
