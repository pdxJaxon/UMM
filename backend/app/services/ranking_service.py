"""Ranking calculation services for candidate evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import random


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


SEVERITY_WEIGHTS = {
    "minor": 0.10,
    "moderate": 0.30,
    "major": 0.65,
    "severe": 1.00,
}
CONFIDENCE_WEIGHTS = {
    "unverified": 0.25,
    "reported": 0.60,
    "verified": 1.00,
}
STATUS_WEIGHTS = {
    "open": 1.00,
    "resolved": 0.50,
    "dismissed": 0.00,
}

POSITION_ALIASES = {
    "OL": "IOL",
    "OG": "IOL",
    "OC": "IOL",
    "C": "IOL",
    "OT": "OT",
    "DL": "DT",
    "DE": "EDGE",
    "OLB": "EDGE",
    "ILB": "LB",
}

POSITION_IMPORTANCE = {
    "QB": 100.0,
    "EDGE": 92.0,
    "OT": 90.0,
    "CB": 88.0,
    "WR": 84.0,
    "DT": 82.0,
    "IOL": 78.0,
    "TE": 68.0,
    "LB": 65.0,
    "S": 60.0,
    "RB": 48.0,
    "FB": 35.0,
    "P": 20.0,
    "K": 18.0,
    "LS": 10.0,
}


def get_position_importance(position: str) -> float:
    """Return a normalized 0-100 baseline importance for an NFL position."""
    normalized_position = position.strip().upper()
    normalized_position = POSITION_ALIASES.get(normalized_position, normalized_position)
    return POSITION_IMPORTANCE.get(normalized_position, 50.0)


def calculate_position_adjusted_ranking(base_ranking: float, position: str, position_weight: float = 0.15) -> float:
    """Blend player evaluation with positional importance for board ordering."""
    if not 0 <= position_weight <= 1:
        raise ValueError("Position weight must be between 0 and 1")
    importance = get_position_importance(position)
    return min(max((base_ranking * (1 - position_weight)) + (importance * position_weight), 0.0), 100.0)


def calculate_derogatory_penalty(concerns: Iterable[Mapping[str, object]]) -> float:
    """Return a capped 0-30 penalty from concern severity, confidence, and status.

    The score is intentionally bounded and explainable. Unknown values contribute no
    penalty until reviewed and mapped to an approved classification.
    """
    penalty = 0.0
    for concern in concerns:
        severity = SEVERITY_WEIGHTS.get(str(concern.get("severity", "")), 0.0)
        confidence = CONFIDENCE_WEIGHTS.get(str(concern.get("confidence", "")), 0.0)
        status = STATUS_WEIGHTS.get(str(concern.get("status", "")), 0.0)
        penalty += 30.0 * severity * confidence * status
    return min(max(penalty, 0.0), 30.0)


def calculate_adjusted_umm_ranking(values: dict[str, float], concerns: Iterable[Mapping[str, object]]) -> float:
    """Return the UMM ranking after applying the bounded derogatory penalty."""
    return max(calculate_umm_ranking(values) - calculate_derogatory_penalty(concerns), 0.0)


def calculate_team_need_score(needs: Iterable[Mapping[str, object]], position: str) -> float:
    """Aggregate multiple same-position needs using diminishing returns.

    The highest active need contributes fully, the second contributes 35%, and
    subsequent needs contribute 15%. Scores are clamped to the 0-100 range.
    """
    normalized_position = POSITION_ALIASES.get(position.strip().upper(), position.strip().upper())
    scores = sorted(
        (
            float(need.get("need_score", 0.0))
            for need in needs
            if need.get("is_active", True)
            and POSITION_ALIASES.get(str(need.get("position_code", "")).upper(), str(need.get("position_code", "")).upper())
            == normalized_position
        ),
        reverse=True,
    )
    if not scores:
        return 0.0
    multipliers = (1.0, 0.35, 0.15)
    return min(max(sum(score * multipliers[min(index, 2)] for index, score in enumerate(scores)), 0.0), 100.0)


def calculate_team_tendency_fit(
    tendencies: Iterable[Mapping[str, object]],
    player: Mapping[str, object],
) -> float:
    """Return a bounded 0-100 fit score for a player against team tendencies.

    Supported tendency types are ``school``, ``conference``, ``measurement``,
    and ``off_field``. Each matching rule contributes its preference multiplied
    by confidence; measurement rules require the configured value range.
    """
    total = 0.0
    weight = 0.0
    player_position = str(player.get("position", "")).upper()
    for tendency in tendencies:
        if not tendency.get("is_active", True):
            continue
        tendency_position = str(tendency.get("position_code") or "").upper()
        if tendency_position and POSITION_ALIASES.get(tendency_position, tendency_position) != POSITION_ALIASES.get(player_position, player_position):
            continue
        if not _tendency_matches(tendency, player):
            continue
        preference = min(max(float(tendency.get("preference_score", 0.0)), 0.0), 100.0)
        confidence = min(max(float(tendency.get("confidence_score", 0.0)), 0.0), 100.0) / 100.0
        contribution_weight = max(confidence, 0.1)
        total += preference * contribution_weight
        weight += contribution_weight
    return min(max(total / weight if weight else 0.0, 0.0), 100.0)


MEETING_IMPORTANCE = {
    "informal": 20.0,
    "formal": 50.0,
    "dinner": 80.0,
    "pro_day": 50.0,
    "facility_invite": 80.0,
}


def calculate_meeting_fit_score(meetings: Iterable[Mapping[str, object]]) -> float:
    """Return a capped 0-100 relationship score from prospect meetings.

    The strongest meeting receives full weight; later meetings add diminishing
    evidence so repeated contact matters without overwhelming player evaluation.
    """
    scores = sorted(
        (
            float(meeting.get("importance_score", MEETING_IMPORTANCE.get(str(meeting.get("meeting_type", "")), 0)))
            for meeting in meetings
            if meeting.get("is_active", True)
        ),
        reverse=True,
    )
    if not scores:
        return 0.0
    multipliers = (1.0, 0.35, 0.15)
    return min(max(sum(score * multipliers[min(index, 2)] for index, score in enumerate(scores)), 0.0), 100.0)


def calculate_external_mock_consensus(
    picks: Iterable[Mapping[str, object]],
    team_id: str,
    pick_number: int,
    maximum_influence: float = 10.0,
) -> list[dict[str, object]]:
    """Rank external player consensus for one team and draft pick.

    The returned influence is capped by ``maximum_influence`` so aggregated
    outside mocks remain a minor signal rather than replacing UMockMe logic.
    """
    counts: dict[str, int] = {}
    for pick in picks:
        if str(pick.get("team_id")) == team_id and int(pick.get("pick_number", -1)) == pick_number:
            player_id = str(pick.get("player_id", ""))
            if player_id:
                counts[player_id] = counts.get(player_id, 0) + 1
    total = sum(counts.values())
    if not total:
        return []
    return [
        {
            "player_id": player_id,
            "mock_count": count,
            "mock_total": total,
            "consensus_percent": round(count / total * 100, 2),
            "influence_score": round(count / total * maximum_influence, 2),
        }
        for player_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def select_with_team_randomness(
    candidates: list[str],
    randomness_score: float,
    rng: random.Random | None = None,
) -> tuple[str, float]:
    """Select a candidate using a bounded team unpredictability score.

    Zero randomness always selects the first candidate. Higher scores increase
    the eligible selection window; the actual factor is returned for audit logs.
    """
    if not candidates:
        raise ValueError("At least one candidate is required")
    score = min(max(float(randomness_score), 0.0), 100.0)
    selection_rng = rng or random.Random()
    window = max(1, min(len(candidates), 1 + int((len(candidates) - 1) * score / 100)))
    return candidates[selection_rng.randrange(window)], score


def _tendency_matches(tendency: Mapping[str, object], player: Mapping[str, object]) -> bool:
    """Determine whether a player satisfies one tendency rule."""
    tendency_type = str(tendency.get("tendency_type", ""))
    if tendency_type == "school":
        return str(player.get("college_id", "")) == str(tendency.get("target_value", ""))
    if tendency_type == "conference":
        return str(player.get("conference", "")) == str(tendency.get("target_value", ""))
    if tendency_type == "off_field":
        return str(player.get("character_profile", "")) == str(tendency.get("target_value", ""))
    if tendency_type == "measurement":
        metric_name = str(tendency.get("metric_name", ""))
        value = player.get("measurements", {}).get(metric_name) if isinstance(player.get("measurements"), Mapping) else None
        if value is None:
            return False
        minimum = tendency.get("minimum_value")
        maximum = tendency.get("maximum_value")
        return (minimum is None or float(value) >= float(minimum)) and (maximum is None or float(value) <= float(maximum))
    return False
