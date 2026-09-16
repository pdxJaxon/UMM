"""Ranking calculation services for candidate evaluation."""

from __future__ import annotations


def calculate_umm_ranking(values: dict[str, float]) -> float:
    """Return a weighted composite ranking score.

    This is the initial trusted implementation for the UMM_Ranking formula used by the
    product specification. The weights are kept centered on public evaluation signals,
    but they can be adjusted through configuration or data versioning in later work.
    """
    weights = {
        "pff": 0.30,
        "nfl": 0.25,
        "sparq": 0.20,
        "school_affinity": 0.15,
        "team_connection": 0.10,
    }

    total_weight = 0.0
    weighted_sum = 0.0

    for key, weight in weights.items():
        if key in values:
            weighted_sum += float(values[key]) * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return min(max(weighted_sum / total_weight, 0.0), 100.0)
