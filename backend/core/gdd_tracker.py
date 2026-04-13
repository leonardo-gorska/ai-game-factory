"""
GORVAX GAME FACTORY — GDD Evolution Tracker (Roadmap v3 Item #13)

Tracks design document evolution across iterations to detect design drift,
removed features, and maintain a decision history.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────


@dataclass
class GDDDiff:
    """Semantic diff between two consecutive GDD snapshots."""

    keys_added: list[str] = field(default_factory=list)
    keys_removed: list[str] = field(default_factory=list)
    keys_changed: list[str] = field(default_factory=list)
    features_added: list[str] = field(default_factory=list)
    features_removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.keys_added or self.keys_removed or self.keys_changed
            or self.features_added or self.features_removed
        )

    @property
    def change_count(self) -> int:
        return (
            len(self.keys_added) + len(self.keys_removed)
            + len(self.keys_changed)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "keys_added": self.keys_added,
            "keys_removed": self.keys_removed,
            "keys_changed": self.keys_changed,
            "features_added": self.features_added,
            "features_removed": self.features_removed,
            "has_changes": self.has_changes,
            "change_count": self.change_count,
        }


@dataclass
class GDDSnapshot:
    """Snapshot of a GDD at a particular iteration."""

    iteration: int
    gdd: dict[str, Any]
    features: set[str] = field(default_factory=set)
    diff: GDDDiff | None = None
    timestamp: float = field(default_factory=time.time)


# ── Feature keywords for extraction ──────────────────

_FEATURE_KEYS = frozenset({
    "mechanics", "features", "systems", "gameplay",
    "abilities", "skills", "items", "enemies",
    "levels", "weapons", "powerups", "upgrades",
    "modes", "resources", "buildings", "units",
    "characters", "quests", "achievements", "events",
})


# ── GDD Tracker ──────────────────────────────────────


class GDDTracker:
    """Tracks GDD evolution across pipeline iterations.

    Records snapshots of the GDD after each designer step, computes
    semantic diffs, detects feature drift, and generates alerts for
    the Critic agent.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: list[GDDSnapshot] = []
        self._max_history = max_history
        # Timeline: feature_name → list of (iteration, "added"|"removed")
        self._feature_timeline: dict[str, list[tuple[int, str]]] = {}

    # ── Recording ─────────────────────────────────────

    def record(self, iteration: int, gdd: dict[str, Any]) -> GDDDiff | None:
        """Record a GDD snapshot and compute diff from previous.

        Returns the diff if there was a previous snapshot, else None.
        """
        if not isinstance(gdd, dict) or not gdd:
            return None

        features = self._extract_features(gdd)

        diff: GDDDiff | None = None
        if self._history:
            prev = self._history[-1]
            diff = self._compute_diff(prev.gdd, gdd, prev.features, features)
            # Update timeline
            for f in diff.features_added:
                self._feature_timeline.setdefault(f, []).append(
                    (iteration, "added")
                )
            for f in diff.features_removed:
                self._feature_timeline.setdefault(f, []).append(
                    (iteration, "removed")
                )
        else:
            # First snapshot — all features are "added"
            for f in features:
                self._feature_timeline.setdefault(f, []).append(
                    (iteration, "added")
                )

        snapshot = GDDSnapshot(
            iteration=iteration,
            gdd=gdd,
            features=features,
            diff=diff,
        )
        self._history.append(snapshot)

        # Prune old history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.debug(
            "GDD tracked iter #%d: %d features, %d changes",
            iteration, len(features),
            diff.change_count if diff else 0,
        )
        return diff

    # ── Drift Alerts ──────────────────────────────────

    def get_drift_alerts(self, last_n: int = 5) -> list[dict[str, Any]]:
        """Generate drift alerts from recent snapshots.

        Alerts are generated for:
        - Features removed without being replaced
        - High churn (features added then removed quickly)
        - Large structural changes (many keys changed at once)
        """
        alerts: list[dict[str, Any]] = []
        recent = self._history[-last_n:] if len(self._history) >= 2 else []

        for snap in recent:
            if snap.diff is None:
                continue

            # Alert: features removed
            if snap.diff.features_removed:
                alerts.append({
                    "type": "features_removed",
                    "severity": "warning",
                    "iteration": snap.iteration,
                    "features": snap.diff.features_removed,
                    "message": (
                        f"Iter #{snap.iteration}: Features removed: "
                        f"{', '.join(snap.diff.features_removed[:5])}"
                    ),
                })

            # Alert: large structural change (>10 keys changed in one iter)
            if snap.diff.change_count > 10:
                alerts.append({
                    "type": "large_change",
                    "severity": "info",
                    "iteration": snap.iteration,
                    "change_count": snap.diff.change_count,
                    "message": (
                        f"Iter #{snap.iteration}: Large GDD change "
                        f"({snap.diff.change_count} keys modified)"
                    ),
                })

        # Alert: feature churn (added then removed within recent window)
        if len(self._history) >= 3:
            recent_features = set()
            for snap in self._history[-last_n:]:
                if snap.diff:
                    for f in snap.diff.features_added:
                        if f in (snap.diff.features_removed or []):
                            continue
                        recent_features.add(f)

            for feature, events in self._feature_timeline.items():
                recent_events = [
                    (it, ev) for it, ev in events
                    if any(s.iteration == it for s in self._history[-last_n:])
                ]
                adds = sum(1 for _, ev in recent_events if ev == "added")
                removes = sum(1 for _, ev in recent_events if ev == "removed")
                if adds >= 1 and removes >= 1:
                    alerts.append({
                        "type": "feature_churn",
                        "severity": "warning",
                        "feature": feature,
                        "message": (
                            f"Feature '{feature}' was added and removed "
                            f"within the last {last_n} iterations (design churn)"
                        ),
                    })

        return alerts

    # ── Feature Timeline ──────────────────────────────

    def get_feature_timeline(self) -> dict[str, list[tuple[int, str]]]:
        """Return the full feature timeline.

        Returns dict mapping feature_name → [(iteration, "added"|"removed"), ...]
        """
        return dict(self._feature_timeline)

    def get_current_features(self) -> set[str]:
        """Return features present in the latest GDD snapshot."""
        if not self._history:
            return set()
        return set(self._history[-1].features)

    # ── Evolution Summary ─────────────────────────────

    def get_evolution_summary(self, last_n: int = 5) -> str:
        """Generate a human-readable evolution summary for prompt injection.

        Returns a compact markdown summary of recent GDD changes.
        """
        if len(self._history) < 2:
            return ""

        recent = self._history[-last_n:]
        lines = ["## GDD Evolution (last iterations)"]

        for snap in recent:
            if snap.diff is None or not snap.diff.has_changes:
                continue
            parts = []
            if snap.diff.features_added:
                parts.append(f"+features: {', '.join(snap.diff.features_added[:3])}")
            if snap.diff.features_removed:
                parts.append(f"-features: {', '.join(snap.diff.features_removed[:3])}")
            if snap.diff.keys_changed:
                parts.append(f"~changed: {len(snap.diff.keys_changed)} keys")
            if parts:
                lines.append(f"- **Iter #{snap.iteration}**: {' | '.join(parts)}")

        # Current feature set
        current = self.get_current_features()
        if current:
            lines.append(f"\n**Active features ({len(current)})**: {', '.join(sorted(current)[:10])}")

        return "\n".join(lines) if len(lines) > 1 else ""

    # ── Stats ─────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return tracker statistics."""
        total_features = len(self._feature_timeline)
        current_features = len(self.get_current_features())
        total_changes = sum(
            s.diff.change_count for s in self._history if s.diff
        )
        return {
            "total_snapshots": len(self._history),
            "total_features_seen": total_features,
            "current_features": current_features,
            "total_changes": total_changes,
            "drift_alerts": len(self.get_drift_alerts()),
        }

    # ── Internal ──────────────────────────────────────

    @staticmethod
    def _extract_features(gdd: dict[str, Any]) -> set[str]:
        """Extract feature names from a GDD dict.

        Walks the GDD recursively looking for feature-related keys
        and collects their string values/keys as feature identifiers.
        """
        features: set[str] = set()

        def _walk(obj: Any, depth: int = 0) -> None:
            if depth > 5:
                return
            if isinstance(obj, dict):
                for key, val in obj.items():
                    key_lower = key.lower()
                    # If key matches feature category, collect sub-keys/values
                    if key_lower in _FEATURE_KEYS:
                        if isinstance(val, dict):
                            features.update(val.keys())
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, str):
                                    features.add(item)
                                elif isinstance(item, dict) and "name" in item:
                                    features.add(str(item["name"]))
                    _walk(val, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item, depth + 1)

        _walk(gdd)
        return features

    @staticmethod
    def _compute_diff(
        old_gdd: dict[str, Any],
        new_gdd: dict[str, Any],
        old_features: set[str],
        new_features: set[str],
    ) -> GDDDiff:
        """Compute semantic diff between two GDD dicts."""
        old_keys = set(_flatten_keys(old_gdd))
        new_keys = set(_flatten_keys(new_gdd))

        keys_added = sorted(new_keys - old_keys)
        keys_removed = sorted(old_keys - new_keys)

        # Changed keys: present in both, but different values
        keys_changed: list[str] = []
        for key in sorted(old_keys & new_keys):
            old_val = _get_nested(old_gdd, key)
            new_val = _get_nested(new_gdd, key)
            if old_val != new_val:
                keys_changed.append(key)

        # Limit to avoid huge diffs
        return GDDDiff(
            keys_added=keys_added[:20],
            keys_removed=keys_removed[:20],
            keys_changed=keys_changed[:20],
            features_added=sorted(new_features - old_features),
            features_removed=sorted(old_features - new_features),
        )


# ── Helpers ───────────────────────────────────────────


def _flatten_keys(d: dict[str, Any], prefix: str = "") -> list[str]:
    """Flatten nested dict keys into dot-notation strings."""
    keys: list[str] = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        keys.append(full)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full))
    return keys


def _get_nested(d: dict[str, Any], key: str) -> Any:
    """Get a value from a nested dict using dot-notation key."""
    parts = key.split(".")
    current: Any = d
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current
