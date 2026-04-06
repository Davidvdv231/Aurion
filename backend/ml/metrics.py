from __future__ import annotations

import numpy as np


def _as_array(values: object) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim == 0:
        return array.reshape(1)
    return array


def mae(actual: object, predicted: object) -> float:
    actual_array = _as_array(actual)
    predicted_array = _as_array(predicted)
    return float(np.mean(np.abs(actual_array - predicted_array)))


def rmse(actual: object, predicted: object) -> float:
    actual_array = _as_array(actual)
    predicted_array = _as_array(predicted)
    return float(np.sqrt(np.mean(np.square(actual_array - predicted_array))))


def mape(actual: object, predicted: object) -> float:
    actual_array = _as_array(actual)
    predicted_array = _as_array(predicted)
    mask = actual_array != 0.0
    if not np.any(mask):
        return 0.0
    return float(
        np.mean(np.abs((actual_array[mask] - predicted_array[mask]) / actual_array[mask])) * 100.0
    )


def directional_accuracy(actual: object, predicted: object) -> float:
    actual_array = _as_array(actual)
    predicted_array = _as_array(predicted)
    if actual_array.size < 2 or predicted_array.size < 2:
        return 0.0
    actual_direction = np.sign(np.diff(actual_array))
    predicted_direction = np.sign(np.diff(predicted_array))
    mask = actual_direction != 0.0
    if not np.any(mask):
        return 0.0
    return float(np.mean(actual_direction[mask] == predicted_direction[mask]))
