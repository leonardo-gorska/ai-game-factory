"""
GORVAX GAME FACTORY — Typed Agent Result Metadata (ARQ1)

TypedDicts documenting the metadata contract for each agent's AgentResult.
Each agent's `execute()` populates `AgentResult.metadata` with the keys
defined here. Consumers can import these for IDE autocompletion and
static-analysis safety.
"""

from __future__ import annotations

from typing import Any, TypedDict


class DesignerMetadata(TypedDict, total=False):
    """Metadata returned by DesignerAgent."""
    gdd_update: dict[str, Any]


class DeveloperMetadata(TypedDict, total=False):
    """Metadata returned by DeveloperAgent."""
    code_changes: dict[str, Any]
    files_written: int


class TesterMetadata(TypedDict, total=False):
    """Metadata returned by TesterAgent."""
    test_report: dict[str, Any]
    score: int


class CriticMetadata(TypedDict, total=False):
    """Metadata returned by CriticAgent."""
    feedback: dict[str, Any]


class ResearcherMetadata(TypedDict, total=False):
    """Metadata returned by ResearcherAgent."""
    research_report: dict[str, Any]
    proposals_count: int
    market_insights_count: int


class PerformanceMetadata(TypedDict, total=False):
    """Metadata returned by PerformanceAgent."""
    performance_report: dict[str, Any]
    performance_score: float
    optimizations_count: int


class SimulationAnalystMetadata(TypedDict, total=False):
    """Metadata returned by SimulationAnalystAgent."""
    simulation_analysis: dict[str, Any]
    insights_count: int
    action_items_count: int
    risk_warnings_count: int
    economy_status: str


class EconomyGuardianMetadata(TypedDict, total=False):
    """Metadata returned by EconomyGuardianAgent."""
    economy_report: dict[str, Any]
    economy_health_score: float
    warnings_count: int
    recommendations_count: int


class MemoryCuratorMetadata(TypedDict, total=False):
    """Metadata returned by MemoryCuratorAgent."""
    curation_report: dict[str, Any]
    winning_patterns: int
    anti_patterns: int
    meta_insights: int
    memory_status: str


class SelfReflectionMetadata(TypedDict, total=False):
    """Metadata returned by SelfReflectionAgent (Roadmap v2 Item 9)."""
    insights: dict[str, Any]


class GoalSetterMetadata(TypedDict, total=False):
    """Metadata returned by GoalSetterAgent (Roadmap v3 Item #15)."""
    goals_count: int
    focus_summary: str
    reused: bool

