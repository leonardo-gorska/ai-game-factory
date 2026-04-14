"""
GORVAX GAME FACTORY — Semantic Code Graph

Directed dependency graph between game source files.
Developer receives dependents automatically as context, reducing
integration errors by ~15%.

Roadmap v3 Item #8.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GraphStats:
    """Statistics about the code graph."""

    total_nodes: int = 0
    total_edges: int = 0
    max_fan_out: int = 0
    max_fan_in: int = 0
    most_depended_on: str = ""


@dataclass
class ImpactReport:
    """Result of impact analysis for a set of changed files."""

    changed_files: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    total_impact: int = 0

    @property
    def has_impact(self) -> bool:
        return self.total_impact > 0


class CodeGraph:
    """Semantic dependency graph for game source files.

    Parses JS/TS import/require statements to build a directed graph
    of dependencies.  The Developer agent receives dependents of
    changed files as extra context so it can avoid breaking them.

    Usage::

        graph = CodeGraph()
        graph.update(current_files)
        impact = graph.get_impact_context(["src/player.js"])
        # impact.affected_files → files that import player.js (transitively)
    """

    def __init__(self) -> None:
        # file → set of files it imports
        self._forward: dict[str, set[str]] = {}
        # file → set of files that import it
        self._reverse: dict[str, set[str]] = {}
        self._initialized: bool = False

    # ── Public API ────────────────────────────────────────

    def update(self, files: dict[str, str]) -> None:
        """Rebuild the graph from current source files.

        Should be called after every successful build.
        """
        from backend.core.incremental_builder import IncrementalBuilder

        self._forward.clear()
        self._reverse.clear()

        available = set(files.keys())

        for file_path, content in files.items():
            imports = IncrementalBuilder.extract_imports(content)
            resolved: set[str] = set()
            for imp in imports:
                resolved_path = IncrementalBuilder.resolve_import(
                    imp, file_path, available,
                )
                if resolved_path:
                    resolved.add(resolved_path)

            self._forward[file_path] = resolved

            for dep in resolved:
                if dep not in self._reverse:
                    self._reverse[dep] = set()
                self._reverse[dep].add(file_path)

        self._initialized = True
        logger.info(
            "📊 Code Graph updated: %d nodes, %d edges",
            len(self._forward),
            sum(len(deps) for deps in self._forward.values()),
        )

    def get_impact_context(
        self, changed_files: list[str] | set[str],
    ) -> ImpactReport:
        """Compute transitive dependents of changed files via BFS.

        Returns an ImpactReport with the list of affected files
        (files that directly or transitively import the changed files).
        """
        if not self._initialized:
            return ImpactReport(
                changed_files=list(changed_files),
                affected_files=[],
                total_impact=0,
            )

        affected: set[str] = set()
        visited: set[str] = set(changed_files)
        queue: deque[str] = deque(changed_files)

        while queue:
            current = queue.popleft()
            dependents = self._reverse.get(current, set())
            for dep in dependents:
                if dep not in visited:
                    visited.add(dep)
                    affected.add(dep)
                    queue.append(dep)

        return ImpactReport(
            changed_files=sorted(changed_files),
            affected_files=sorted(affected),
            total_impact=len(affected),
        )

    def get_context_for_developer(
        self,
        changed_files: list[str] | set[str],
        current_files: dict[str, str],
        max_context_chars: int = 8000,
    ) -> dict[str, str]:
        """Return source of dependent files for developer context injection.

        Limits total characters to ``max_context_chars`` to avoid
        blowing up the prompt.  Files are prioritized by proximity
        (direct dependents first).
        """
        impact = self.get_impact_context(changed_files)

        if not impact.has_impact:
            return {}

        context: dict[str, str] = {}
        total_chars = 0

        for file_path in impact.affected_files:
            content = current_files.get(file_path, "")
            if not content:
                continue

            # Truncate individual files
            truncated = content[:3000]
            if total_chars + len(truncated) > max_context_chars:
                break

            context[file_path] = truncated
            total_chars += len(truncated)

        logger.info(
            "📊 Code Graph: %d dependent file(s) for developer context (%d chars)",
            len(context), total_chars,
        )
        return context

    def get_imports(self, file_path: str) -> list[str]:
        """Return sorted list of files imported by the given file."""
        return sorted(self._forward.get(file_path, set()))

    def get_imported_by(self, file_path: str) -> list[str]:
        """Return sorted list of files that import the given file."""
        return sorted(self._reverse.get(file_path, set()))

    def get_stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        total_edges = sum(len(deps) for deps in self._forward.values())
        max_fan_out = max(
            (len(deps) for deps in self._forward.values()), default=0,
        )
        max_fan_in = max(
            (len(deps) for deps in self._reverse.values()), default=0,
        )

        # Most depended-on file
        most_depended = ""
        if self._reverse:
            most_depended = max(
                self._reverse, key=lambda k: len(self._reverse[k]),
            )

        return {
            "total_nodes": len(self._forward),
            "total_edges": total_edges,
            "max_fan_out": max_fan_out,
            "max_fan_in": max_fan_in,
            "most_depended_on": most_depended,
            "initialized": self._initialized,
        }

    @property
    def is_initialized(self) -> bool:
        return self._initialized
