"""Explainable continuity and variety rules over technical scores."""

from __future__ import annotations

from typing import Any


DECISION_LABELS = {
    "highest_score": "Highest technical score",
    "quality_switch": "Alternative exceeded the camera-change threshold",
    "continuity_rule": "Current camera was unavailable; selected best available alternative",
    "mandatory_variety": "Best acceptable alternative after the continuity limit",
    "compliance_repair": "Acceptable alternative selected to improve camera variety",
    "human_override": "Changed by the reviewer",
}


def _eligible(candidates: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    values = [
        (camera_id, data) for camera_id, data in candidates.items()
        if data.get("available", True) and not data.get("black_frame", False)
    ]
    return sorted(values, key=lambda item: (-float(item[1].get("technical_score", 0.0)), item[0]))


def count_switches(camera_ids: list[str]) -> int:
    return sum(previous != current for previous, current in zip(camera_ids, camera_ids[1:]))


def _selection(camera_id: str, data: dict[str, Any], source: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "camera_id": camera_id,
        "technical_score": float(data.get("technical_score", 0.0)),
        "component_scores": data.get("component_scores", {}),
        "decision_source": source,
        "reason": reason or DECISION_LABELS[source],
    }


def _repair(sequence: list[dict[str, Any]], candidates_by_segment: list[dict[str, dict[str, Any]]], config: dict[str, Any]) -> None:
    target_distinct, target_switches = 2, 3
    # Fewer than four fixed windows can never satisfy the three-switch target.
    # Leave technical recommendations intact instead of manufacturing a partial repair.
    if len(sequence) < target_switches + 1:
        return
    for _ in range(len(sequence) * 2):
        chosen_ids = [item["camera_id"] for item in sequence]
        before = (len(set(chosen_ids)), count_switches(chosen_ids))
        if before[0] >= target_distinct and before[1] >= target_switches:
            return
        best_change: tuple[tuple[int, int], int, str, dict[str, Any]] | None = None
        for index, choice in enumerate(sequence):
            original_score = choice["technical_score"]
            for alternative_id, alternative in _eligible(candidates_by_segment[index]):
                if alternative_id == choice["camera_id"]:
                    continue
                alternative_score = float(alternative.get("technical_score", 0.0))
                if alternative_score < config["quality_floor"] or original_score - alternative_score > config["repair_score_gap"]:
                    continue
                revised = chosen_ids.copy()
                revised[index] = alternative_id
                improvement = (len(set(revised)), count_switches(revised))
                if improvement <= before:
                    continue
                candidate = (improvement, index, alternative_id, alternative)
                if best_change is None or candidate[0] > best_change[0] or (candidate[0] == best_change[0] and candidate[1:3] < best_change[1:3]):
                    best_change = candidate
        if best_change is None:
            return
        _, index, camera_id, data = best_change
        sequence[index] = _selection(camera_id, data, "compliance_repair")


def recommend_cameras(candidates_by_segment: list[dict[str, dict[str, Any]]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Choose camera IDs while keeping technical scoring independent from variety policy."""
    sequence: list[dict[str, Any]] = []
    current_id: str | None = None
    consecutive = 0
    for candidates in candidates_by_segment:
        eligible = _eligible(candidates)
        if not eligible:
            sequence.append(_selection("", {}, "continuity_rule", "No usable camera was available for this segment"))
            current_id, consecutive = None, 0
            continue
        highest_id, highest = eligible[0]
        if current_id is None:
            chosen_id, chosen, source = highest_id, highest, "highest_score"
        else:
            current = candidates.get(current_id)
            if current is None or not current.get("available", True) or current.get("black_frame", False):
                chosen_id, chosen, source = highest_id, highest, "continuity_rule"
            elif consecutive >= config["max_consecutive_windows"]:
                alternatives = [(camera_id, data) for camera_id, data in eligible if camera_id != current_id and float(data.get("technical_score", 0)) >= config["quality_floor"]]
                if alternatives:
                    chosen_id, chosen, source = alternatives[0][0], alternatives[0][1], "mandatory_variety"
                else:
                    chosen_id, chosen, source = current_id, current, "continuity_rule"
            elif highest_id != current_id and float(highest.get("technical_score", 0)) >= float(current.get("technical_score", 0)) + config["switch_threshold"]:
                chosen_id, chosen, source = highest_id, highest, "quality_switch"
            else:
                chosen_id, chosen, source = current_id, current, "continuity_rule"
        sequence.append(_selection(chosen_id, chosen, source))
        consecutive = consecutive + 1 if chosen_id == current_id else 1
        current_id = chosen_id
    _repair(sequence, candidates_by_segment, config)
    return sequence
