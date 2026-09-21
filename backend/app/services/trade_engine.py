"""Draft trade evaluation using pick values and historical team tendencies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeProposal:
    """A value-balanced swap between the current pick and a later pick."""

    moving_up_team_id: str
    moving_down_team_id: str
    current_pick_number: int
    acquired_pick_number: int
    current_pick_value: float
    acquired_pick_value: float
    value_delta: float
    evidence: dict[str, object]


def pick_value(pick_number: int) -> float:
    """Return a normalized Jimmy Johnson-style value for a draft pick."""
    if pick_number < 1:
        raise ValueError("Pick number must be positive")
    return round(1000.0 * (0.72 ** (pick_number - 1)), 2)


def evaluate_trade(
    order: Sequence[str],
    pick_index: int,
    tendencies_by_team: Mapping[str, Sequence[Mapping[str, object]]],
) -> TradeProposal | None:
    """Choose a later partner when both teams have a strong historical signal.

    The current team can move down by swapping its pick with a later team's next
    pick. The later team moves up. No trade is executed without both sides having
    an active, confidence-adjusted tendency for that direction.
    """
    if pick_index < 0 or pick_index >= len(order):
        return None
    moving_down_team_id = order[pick_index]
    current_pick_number = pick_index + 1
    current_value = pick_value(current_pick_number)
    down_signal = _direction_signal(tendencies_by_team.get(moving_down_team_id, ()), "trade_down")
    if down_signal is None:
        return None

    best: TradeProposal | None = None
    for later_index in range(pick_index + 1, len(order)):
        moving_up_team_id = order[later_index]
        up_signal = _direction_signal(tendencies_by_team.get(moving_up_team_id, ()), "trade_up")
        if up_signal is None:
            continue
        acquired_pick_number = later_index + 1
        acquired_value = pick_value(acquired_pick_number)
        evidence = {
            "moving_down": down_signal,
            "moving_up": up_signal,
            "chart": "normalized-jimmy-johnson-v1",
        }
        proposal = TradeProposal(
            moving_up_team_id=moving_up_team_id,
            moving_down_team_id=moving_down_team_id,
            current_pick_number=current_pick_number,
            acquired_pick_number=acquired_pick_number,
            current_pick_value=current_value,
            acquired_pick_value=acquired_value,
            value_delta=round(current_value - acquired_value, 2),
            evidence=evidence,
        )
        if best is None or proposal.acquired_pick_number < best.acquired_pick_number:
            best = proposal
    return best


def _direction_signal(
    tendencies: Sequence[Mapping[str, object]],
    tendency_type: str,
) -> dict[str, object] | None:
    """Return the strongest confidence-adjusted historical direction signal."""
    matching = [
        tendency for tendency in tendencies
        if tendency.get("tendency_type") == tendency_type and tendency.get("is_active", True)
    ]
    if not matching:
        return None
    tendency = max(
        matching,
        key=lambda item: float(item.get("preference_score", 0)) * float(item.get("confidence_score", 0)) / 100,
    )
    willingness = round(
        min(max(float(tendency.get("preference_score", 0)), 0), 100)
        * min(max(float(tendency.get("confidence_score", 0)), 0), 100)
        / 100,
        2,
    )
    if willingness < 60:
        return None
    return {
        "preference_score": float(tendency.get("preference_score", 0)),
        "confidence_score": float(tendency.get("confidence_score", 0)),
        "willingness_score": willingness,
        "sample_size": int(tendency.get("sample_size", 0)),
        "source_name": tendency.get("source_name"),
        "rationale": tendency.get("rationale"),
    }