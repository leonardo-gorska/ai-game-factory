"""
GORVAX GAME FACTORY — Pipeline v5
Orchestrador evolutivo com hardening 24/7 + agentes especializados:
Researcher → Designer → Developer → Build → Performance → Simulate →
Exploit Detect → Sim Analyst → Economy Guardian → Test → Novelty →
Quality → Diff → Critic → Stagnation Guard → Cost Check →
Experiment Log → Memory Curator (every 5 iters)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from typing import Any, Callable, Awaitable, TypedDict

from backend.agents.designer_agent import DesignerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.fixer_agent import FixerAgent
from backend.agents.tester_agent import TesterAgent
from backend.agents.critic_agent import CriticAgent
from backend.agents.performance_agent import PerformanceAgent
from backend.agents.researcher_agent import ResearcherAgent
from backend.agents.simulation_analyst_agent import SimulationAnalystAgent
from backend.agents.economy_guardian_agent import EconomyGuardianAgent
from backend.agents.memory_curator_agent import MemoryCuratorAgent
from backend.agents.self_reflection import SelfReflectionAgent
from backend.core.quality_engine import QualityEngine, QualityMetrics
from backend.core.diff_analyzer import DiffAnalyzer
from backend.core.cost_guard import CostGuard, CostBudget
from backend.core.stagnation_guard import StagnationGuard
from backend.core.novelty_engine import NoveltyEngine
from backend.core.watchdog import Watchdog
from backend.core.game_roadmap import GameRoadmap
from backend.llm.prompt_versioner import check_and_log_changes as _check_prompts
from backend.core.experiment_tracker import ExperimentTracker
from backend.core.game_benchmarks import BenchmarkComparator
from backend.llm.model_manager import ModelManager
from backend.core.exploit_detector import ExploitDetector
from backend.core.exploration_controller import ExplorationController
from backend.game.builder import GameBuilder
from backend.game.evaluator import GameEvaluator
from backend.game.simulator import PlaytestSimulator
from backend.game.versioner import GameVersioner
from backend.llm.router import LLMRouter
from backend.orchestrator.state import PipelineState
from backend.storage.database import Database
from backend.config import get_config, AppConfig, GAME_DIR
from backend.llm.prompt_engine import PromptEngine
from backend.storage.chat_store import get_chat_store
from backend.storage.session_logger import get_session_logger

# Optional: Vector Memory (graceful if chromadb not installed)
try:
    from backend.memory.experience_db import ExperienceDB
    from backend.memory.vector_store import VectorStore
    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False

# Optional: Headless Browser Tester (graceful if playwright not installed)
try:
    from backend.game.headless_tester import HeadlessTester
    _HEADLESS_AVAILABLE = True
except ImportError:
    _HEADLESS_AVAILABLE = False

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

# ── Adaptive retry strategies for _build_with_retries ─────
RETRY_STRATEGIES: list[dict[str, Any]] = [
    {"temperature": 0.7, "model_tier": "default"},   # Retry 1: normal creativity
    {"temperature": 0.3, "model_tier": "default"},   # Retry 2: deterministic
    {"temperature": 0.5, "model_tier": "premium"},   # Retry 3+: best model
]


class _PipelineStopRequested(Exception):
    """Raised internally to abort the current iteration when stop/pause is requested."""
    pass


# ── TypedDicts for step results (BE-17) ──────────────

class DesignerStepResult(TypedDict, total=False):
    """Result from the Designer agent step."""
    gdd_update: dict[str, Any]
    exploration_mode: bool


class DeveloperStepResult(TypedDict, total=False):
    """Result from the Developer agent step."""
    code_changes: dict[str, str]
    files_modified: list[str]


class BuildStepResult(TypedDict):
    """Result from the build + lint step."""
    success: bool
    output: str


class QualityStepResult(TypedDict, total=False):
    """Result from the quality evaluation step."""
    composite: float
    fun: float
    stability: float
    performance: float
    balance: float
    novelty: float
    retention: float
    regression_penalty: float
    confidence_lower: float
    confidence_upper: float


class IterationResult(TypedDict, total=False):
    """Complete result of a single pipeline iteration."""
    iteration: int
    score: int
    build_success: bool
    quality: QualityStepResult
    designer: DesignerStepResult
    developer: DeveloperStepResult
    build: BuildStepResult
    test_report: dict[str, Any]
    critic_feedback: dict[str, Any]
    diff_risk: str
    novelty_score: float
    exploration_mode: bool
    cost_usd: float
    is_milestone: bool
    error: str | None


class Pipeline:
    """
    Orchestrador evolutivo v5 do GORVAX GAME FACTORY.

    Loop completo por iteração (17 steps):
    1.  Researcher → pesquisa features e inovações
    2.  Designer → atualiza GDD com insights do Researcher
    3.  Developer → escreve código
    4.  Build + Lint → valida compilação
    5.  Performance Agent → analisa bundle, game loops, memory leaks
    6.  Simulator → playtest automatizado (4 perfis, 50+ runs)
    7.  Exploit Detector → scan de exploits
    8.  Simulation Analyst → interpreta dados de simulação
    9.  Economy Guardian → análise profunda de economia
    10. Tester → avaliação LLM com dados de simulação + análise
    11. Novelty Engine → cálculo de diversidade
    12. Quality Engine → score multi-objetivo
    13. Diff Analyzer → análise de risco
    14. Critic → análise estratégica + instruções
    15. Stagnation Guard → detecta platô, ativa exploração ou rollback
    16. Cost Guard → verifica budget
    17. Experiment Tracker → snapshot completo da iteração
    +   Memory Curator → curadoria de memória (a cada 5 iterações)

    Hardening:
    - Watchdog → monitora timeouts, crashes, cost spikes, disk space
    - Smart Router → roteamento LLM por custo × latência × complexidade
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        self.state = PipelineState()
        self.database = Database()

        # Core systems
        self.cost_guard = CostGuard(CostBudget())
        self.quality_engine = QualityEngine()
        self.diff_analyzer = DiffAnalyzer()
        self.simulator = PlaytestSimulator()

        # v3: Evolutionary intelligence
        self.stagnation_guard = StagnationGuard()
        self.novelty_engine = NoveltyEngine()

        # v4: Hardening systems
        self.watchdog = Watchdog()
        self.experiment_tracker = ExperimentTracker()
        self.exploit_detector = ExploitDetector()
        self.exploration_controller = ExplorationController()

        # P11: Headless browser tester (optional)
        self.headless_tester: Any = None
        if _HEADLESS_AVAILABLE:
            try:
                self.headless_tester = HeadlessTester(
                    game_url=f"http://localhost:{self._config.server.game_port}",
                    screenshot_dir=GAME_DIR.parent / "data" / "screenshots",
                )
                logger.info("✅ Headless Browser Tester (Playwright) loaded")
            except Exception as exc:
                logger.warning("Headless tester init failed: %s", exc)

        # v3: Vector Memory (optional)
        self.experience_db: Any = None
        if _MEMORY_AVAILABLE:
            try:
                vs = VectorStore()
                self.experience_db = ExperienceDB(vs)
                logger.info("✅ Vector Memory (ChromaDB) carregado")
            except Exception as exc:
                logger.warning("Vector Memory indisponível: %s", exc)

        # LLM Router v3 com smart routing + cost tracking
        self.llm_router = LLMRouter(cost_guard=self.cost_guard)

        # Game tools
        self.builder = GameBuilder()
        self.evaluator = GameEvaluator()
        self.versioner = GameVersioner()

        # Prompt Engine — renders templates with project config
        self.prompt_engine = PromptEngine(self._config.project)

        # Game Roadmap — tracks phased development progress
        self.roadmap = GameRoadmap(GAME_DIR / "src")

        # Agents (9 agents) — prompts rendered per project config
        agent_kwargs: dict[str, Any] = {
            "llm_router": self.llm_router,
            "database": self.database,
        }
        if self.experience_db:
            agent_kwargs["experience_db"] = self.experience_db

        self.researcher = ResearcherAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("researcher"))
        self.designer = DesignerAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("designer"))
        self.developer = DeveloperAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("developer"))
        self.tester = TesterAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("tester"))
        self.critic = CriticAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("critic"))
        self.performance_agent = PerformanceAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("performance"))
        self.simulation_analyst = SimulationAnalystAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("simulation_analyst"))
        self.economy_guardian = EconomyGuardianAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("economy_guardian"))
        self.memory_curator = MemoryCuratorAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("memory_curator"))

        # v3 Fixer Agent: specialized debugging agent for build/runtime error fixes
        self.fixer = FixerAgent(**agent_kwargs, system_prompt=self.prompt_engine.render("fixer"))

        # v2 Roadmap Item 9: Self-Reflection Agent (meta-analysis every 10 iters)
        self.self_reflection = SelfReflectionAgent(
            **agent_kwargs,
            system_prompt=self.prompt_engine.render("self_reflection"),
            interval=10,
        )

        # Previous economy report for trend tracking
        self._previous_economy_report: dict[str, Any] = {}
        self._last_novelty_score: float = 0.0  # PIP-03: declared explicitly
        self._last_heatmap: dict[str, Any] = {}  # API-01: declared explicitly (no hasattr)

        # Auto-skip stale agents — reuse previous results when input unchanged
        self._last_agent_results: dict[str, dict[str, Any]] = {}
        self._last_perf_score: float = 50.0

        # Agent result cache — avoids redundant LLM calls
        from backend.core.agent_cache import AgentCache
        self.agent_cache = AgentCache(default_ttl=3)

        # v2 Roadmap: Agent Specialization Router
        from backend.core.agent_router import AgentRouter
        self.agent_router = AgentRouter(full_sweep_interval=5)

        # v2 Roadmap: Progressive Complexity Manager
        from backend.core.complexity_manager import ComplexityManager
        self.complexity_manager = ComplexityManager()

        # v2 Roadmap: Incremental Builder — partial rebuilds
        from backend.core.incremental_builder import IncrementalBuilder
        self.incremental_builder = IncrementalBuilder()

        # v2 Roadmap: Template Library
        from backend.templates.registry import TemplateRegistry
        self.template_registry = TemplateRegistry()

        # v2 Roadmap: Feedback Loop Assíncrono — parallel analysis prep
        from backend.core.analysis_context_preparer import AnalysisContextPreparer
        self.analysis_preparer = AnalysisContextPreparer(self)

        # v2 Roadmap Item 10: Competitive Benchmark
        self.benchmark_comparator = BenchmarkComparator()

        # v2 Roadmap Item 11: Hot-Swap de Modelo em Runtime
        self.model_manager = ModelManager()

        # v2 Roadmap Item 5: Multi-Model Consensus (Ensemble)
        from backend.llm.ensemble import EnsembleRouter
        self.ensemble_router = EnsembleRouter(self.llm_router)
        self.llm_router.set_ensemble_router(self.ensemble_router)

        # v3 Roadmap Item 1: Parallel Agent Pipeline
        from backend.orchestrator.parallel_scheduler import ParallelScheduler
        self.parallel_scheduler = ParallelScheduler()

        # v3 Roadmap Item 2: Error Pattern Database
        from backend.core.error_pattern_db import ErrorPatternDB
        self.error_pattern_db = ErrorPatternDB(
            GAME_DIR.parent / "data" / "error_patterns.json"
        )

        # v3 Roadmap Item 7: Dynamic Agent Temperature
        from backend.core.temperature_controller import TemperatureController
        self.temperature_controller = TemperatureController()
        self.llm_router.set_temperature_controller(self.temperature_controller)

        # v3 Roadmap Item 6: Predictive Build Failure
        from backend.core.build_predictor import BuildPredictor
        self.build_predictor = BuildPredictor()

        # v3 Roadmap Item 8: Semantic Code Graph
        from backend.core.code_graph import CodeGraph
        self.code_graph = CodeGraph()

        # v3 Roadmap Item 9: Agent Specialization Fork
        from backend.agents.agent_forker import AgentForker
        self.agent_forker = AgentForker()

        # v3 Roadmap Item 10: Automated Regression Suite
        from backend.core.regression_suite import RegressionSuite
        self.regression_suite = RegressionSuite(
            GAME_DIR.parent / "data" / "regression_tests"
        )

        # v3 Roadmap Item 11: Cost-Aware Routing Intelligence
        from backend.llm.cost_optimizer import CostOptimizer
        self.cost_optimizer = CostOptimizer()
        self.llm_router.set_cost_optimizer(self.cost_optimizer)

        # v3 Roadmap Item 12: Pipeline Replay & Debug Mode
        from backend.core.pipeline_journal import PipelineJournal
        self.pipeline_journal = PipelineJournal(
            journal_dir=GAME_DIR.parent / "data" / "journal",
        )

        # v3 Roadmap Item 13: GDD Evolution Tracker
        from backend.core.gdd_tracker import GDDTracker
        self.gdd_tracker = GDDTracker()

        # v3 Roadmap Item 14: Agent Confidence Scoring
        from backend.core.confidence_scorer import ConfidenceScorer
        self.confidence_scorer = ConfidenceScorer()

        # v3 Roadmap Item 15: Autonomous Goal Setting
        from backend.agents.goal_setter_agent import GoalSetterAgent
        self.goal_setter = GoalSetterAgent(
            **agent_kwargs,
            system_prompt=self.prompt_engine.render("goal_setter") or GoalSetterAgent._default_system_prompt(),
        )
        self._last_goals: dict[str, Any] = {}

        self._event_callbacks: list[EventCallback] = []
        self._stop_requested = False
        self._previous_files: dict[str, str] = {}
        self._previous_metrics: QualityMetrics | None = None

        # P4: Context accumulation for Developer agent
        self._last_test_report: dict[str, Any] = {}
        self._last_critic_feedback: dict[str, Any] = {}
        self._last_quality_breakdown: dict[str, Any] = {}
        self._known_bugs: list[str] = []
        self._previous_build_success: bool = False  # v2.3 P3: track for rollback detection

        # P5: Build productivity tracking
        self._file_hashes: dict[str, str] = {}    # filename → md5
        self._failed_fixes: list[dict[str, str]] = []  # log of failed fix attempts
        self._last_build_hash: str = ""            # hash of all src files
        self._last_build_errors: list = []          # previous build's ClassifiedErrors
        self._metrics: dict[str, int] = {
            "builds_total": 0,
            "builds_passed": 0,
            "builds_failed": 0,
            "builds_cached": 0,
            "retries_total": 0,
            "retries_succeeded": 0,
            "retries_adaptive": 0,
            "tasks_skipped": 0,
            "snapshots_saved": 0,
            "snapshots_restored": 0,
            "imports_fixed": 0,
            "prompts_compressed": 0,
            "errors_diff_computed": 0,
            "cost_predictions_warned": 0,
            "snapshots_pruned": 0,
            "quality_gate_blocked": 0,
            "auto_fixes_applied": 0,
            "auto_fix_builds_saved": 0,
            "agents_routed_skipped": 0,
            "phase_transitions": 0,
            "templates_suggested": 0,
            "incremental_builds": 0,
            "incremental_files_skipped": 0,
            "incremental_full_rebuilds": 0,
            "analysis_prep_parallel": 0,
            "analysis_prep_time_saved_ms": 0,
            "benchmark_comparisons": 0,
            "model_swaps": 0,
            "self_reflections": 0,
            "ensemble_calls": 0,
            "error_db_hits": 0,
            "error_db_misses": 0,
            "parallel_waves_count": 0,
            "temperature_adjustments": 0,
            "build_predictions": 0,
            "build_predictions_correct": 0,
            "code_graph_updates": 0,
            "code_graph_context_files": 0,
            "agent_forks_detected": 0,
            "agent_forks_executed": 0,
            "agent_fork_conflicts": 0,
            "regression_tests_run": 0,
            "regression_tests_passed": 0,
            "regression_tests_generated": 0,
            "cost_optimizer_records": 0,
            "journal_entries": 0,
            "journal_replays": 0,
            "gdd_snapshots_tracked": 0,
            "gdd_drift_alerts": 0,
            "confidence_retries": 0,
            "goal_sets_generated": 0,
            "goal_sets_reused": 0,
            "fixer_fixes": 0,
            "fixer_runtime_fixes": 0,
            "fixer_render_fixes": 0,
        }

        # v3 Item 10: Regression result for tester_step
        self._regression_result: dict[str, Any] = {}

    def on_event(self, callback: EventCallback) -> None:
        """Register event callback for real-time updates."""
        self._event_callbacks.append(callback)
        all_agents = [
            self.researcher, self.designer, self.developer,
            self.tester, self.critic, self.performance_agent,
            self.simulation_analyst, self.economy_guardian,
            self.memory_curator, self.goal_setter,
        ]
        for agent in all_agents:
            agent.on_event(callback)
            # v3 Item #12: Share journal with all agents
            agent.journal = self.pipeline_journal
            agent.confidence_scorer = self.confidence_scorer

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        event = {"type": event_type, "data": data}
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except Exception as exc:
                logger.warning("Event callback error: %s", exc)

    async def emit_chat(
        self,
        agent: str,
        message: str,
        iteration: int = 0,
        msg_type: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a humanized chat message to the dashboard."""
        store = get_chat_store()
        msg = store.add(agent, message, iteration, msg_type, metadata)
        await self._emit("agent_message", msg.to_dict())

    # ── Lifecycle ──────────────────────────────────────

    async def start(self, max_iterations: int | None = None) -> None:
        """Start the pipeline loop."""
        max_iter = max_iterations or self._config.pipeline.max_iterations
        delay = self._config.pipeline.iteration_delay_seconds

        await self.database.connect()
        self.state.is_running = True
        self._stop_requested = False

        # Start log session
        get_session_logger().start_session()

        last = await self.database.get_latest_iteration_number()
        if last > 0:
            self.state.current_iteration = last
            logger.info("Retomando da iteração %d", last)

        # Carregar snapshot dos arquivos atuais para diff
        self._previous_files = self.diff_analyzer.get_current_files()

        # v4: Start Watchdog background monitoring
        await self.watchdog.start()

        # ━━ Step 0: Environment Auto-Setup ━━━━━━━━━━━━━━━━━━━
        await self.emit_chat(
            "pipeline",
            "🔧 Verificando ambiente de build (Node.js, npm, dependências)...",
            0, "thinking",
        )
        try:
            env = await self.builder.check_environment()
            if not env["ok"]:
                errors = "; ".join(env["errors"])
                logger.error("❌ Environment check failed: %s", errors)
                await self.emit_chat(
                    "pipeline",
                    f"❌ Ambiente não está pronto: {errors}\n"
                    "Instale Node.js em https://nodejs.org/ e reinicie.",
                    0, "error",
                )
                self.state.is_running = False
                return

            parts = [f"✅ Ambiente pronto! Node {env['node_version']}, npm v{env['npm_version']}"]
            if env.get("npm_installed"):
                parts.append("📦 Dependências instaladas automaticamente")
            await self.emit_chat("pipeline", " | ".join(parts), 0, "success")
        except Exception as exc:
            logger.warning("Environment check failed (non-blocking): %s", exc)
            await self.emit_chat(
                "pipeline",
                f"⚠️ Verificação de ambiente falhou ({exc}), tentando continuar...",
                0, "warning",
            )

        await self._emit("pipeline_start", {
            "max_iterations": max_iter,
            "providers": self.llm_router.available_providers,
            "routing": self.llm_router.get_routing_info(),
            "features": {
                "watchdog": True,
                "performance_agent": True,
                "experiment_tracker": True,
                "smart_router": True,
                "stagnation_guard": True,
                "novelty_engine": True,
                "vector_memory": self.experience_db is not None,
                "player_profiles": True,
            },
        })

        logger.info(
            "🚀 GORVAX GAME FACTORY v4 iniciada! Max: %d iterações | "
            "Providers: %s | Memory: %s | Watchdog: ON",
            max_iter, self.llm_router.available_providers,
            "ON" if self.experience_db else "OFF",
        )

        # P7: Load persisted agent memories from disk
        memory_dir = GAME_DIR.parent / "data" / "memory"
        for agent in [self.designer, self.developer, self.tester, self.critic,
                      self.performance_agent, self.researcher, self.simulation_analyst,
                      self.economy_guardian, self.memory_curator]:
            try:
                agent.memory.load_from_disk(memory_dir)
            except Exception as exc:
                logger.debug("Could not load memory for %s: %s", agent.name, exc)

        # #17: Detect prompt template changes
        try:
            _check_prompts()
        except Exception as exc:
            logger.debug("Prompt version check failed: %s", exc)

        _watchdog_auto_pauses = 0
        _WATCHDOG_COOLDOWN_SHORT = 15   # seconds
        _WATCHDOG_COOLDOWN_LONG = 60    # after every 5 pauses

        # v2.2: Quality threshold — if game is still broken (score < 40),
        # extend iterations beyond max_iter (up to 1.5x as absolute cap)
        _MIN_QUALITY_THRESHOLD = 40.0
        _ABSOLUTE_MAX_FACTOR = 1.5
        _last_quality_score: float = 0.0  # updated at end of each iteration

        try:
            while (
                not self._stop_requested
                and (
                    self.state.total_iterations < max_iter
                    or (
                        _last_quality_score < _MIN_QUALITY_THRESHOLD
                        and self.state.total_iterations < int(max_iter * _ABSOLUTE_MAX_FACTOR)
                    )
                )
            ):
                # v4: Check watchdog pause/abort requests — auto-resume always
                if self.watchdog.pause_requested:
                    _watchdog_auto_pauses += 1
                    self.watchdog.clear_pause_request()
                    health = self.watchdog.get_health()
                    reason = "causa desconhecida"
                    if health.consecutive_failures >= 3:
                        reason = f"{health.consecutive_failures} falhas consecutivas"
                    elif health.active_alerts:
                        reason = health.active_alerts[0].get("message", reason)

                    # Progressive cooldown: longer pause every 5 failures
                    cooldown = (
                        _WATCHDOG_COOLDOWN_LONG
                        if _watchdog_auto_pauses % 5 == 0
                        else _WATCHDOG_COOLDOWN_SHORT
                    )

                    logger.warning(
                        "🐕 Watchdog auto-pause #%d: %s — retomando em %ds",
                        _watchdog_auto_pauses, reason, cooldown,
                    )
                    await self.emit_chat(
                        "watchdog",
                        f"⚠️ Problema detectado: {reason}. "
                        f"Aguardando {cooldown}s e retomando automaticamente... "
                        f"(auto-recuperação #{_watchdog_auto_pauses})",
                        self.state.current_iteration, "warning",
                    )
                    await self._emit("watchdog_pause", {
                        "health": health.to_dict(),
                        "action": "auto_resume",
                        "resume_in_seconds": cooldown,
                        "auto_pause_count": _watchdog_auto_pauses,
                    })

                    # Wait and then auto-resume — never stop
                    await asyncio.sleep(cooldown)

                    # Reset watchdog failure counter to give a fresh chance
                    self.watchdog.reset_consecutive_failures()
                    await self.emit_chat(
                        "watchdog",
                        f"▶️ Retomando pipeline (falhas resetadas, tentativa #{_watchdog_auto_pauses + 1})",
                        self.state.current_iteration, "system",
                    )
                    continue

                # Handle manual pause (from user button)
                while self.state.is_paused and not self._stop_requested:
                    await asyncio.sleep(1)

                if self._stop_requested:
                    break

                await self._run_iteration()

                # v2.2: Track last quality score for threshold checking
                if self.state.history and self.state.history[-1].score > 0:
                    _last_quality_score = float(self.state.history[-1].score)

                # Reset watchdog auto-pause counter on successful iteration
                if self.state.history and self.state.history[-1].score > 0:
                    _watchdog_auto_pauses = 0

                if delay > 0 and not self._stop_requested:
                    await self._emit("pipeline_waiting", {"delay": delay})
                    await asyncio.sleep(delay)

        except Exception as exc:
            logger.error("Pipeline error: %s", exc)
            await self._emit("pipeline_error", {"error": str(exc)})

        finally:
            self.state.is_running = False
            await self.watchdog.stop()
            get_session_logger().end_session()
            await self._emit("pipeline_stop", self.state.to_dict())
            await self.database.close()
            logger.info(
                "Pipeline parou após %d iterações | Custo total: $%.4f",
                self.state.total_iterations,
                self.cost_guard.get_stats()["total_cost_usd"],
            )

    async def stop(self) -> None:
        self._stop_requested = True
        logger.info("⛔ Stop solicitado — abortando iteração atual...")

    async def pause(self) -> None:
        self.state.is_paused = True
        logger.info("⏸️ Pause solicitado")
        await self._emit("pipeline_paused", {})

    async def resume(self) -> None:
        self.state.is_paused = False
        logger.info("▶️ Resume solicitado")
        await self._emit("pipeline_resumed", {})

    async def _check_stop_or_pause(self, step_name: str = "") -> None:
        """Check if stop/pause was requested. Call between steps.

        - If paused, blocks here until resumed or stopped.
        - If stop requested (or watchdog abort), raises _PipelineStopRequested.
        """
        # Handle pause: block until resumed
        while self.state.is_paused and not self._stop_requested:
            logger.debug("⏸️ Pipeline pausado em '%s', aguardando resume...", step_name)
            await asyncio.sleep(0.5)

        # Handle stop
        if self._stop_requested:
            raise _PipelineStopRequested(f"Stop solicitado durante '{step_name}'")

        # Handle watchdog abort — downgrade to warning, never kill iteration
        if self.watchdog.abort_iteration_requested:
            self.watchdog.clear_abort_request()
            logger.warning(
                "🐕 Watchdog quis abortar '%s' — ignorando, pipeline continua",
                step_name,
            )

    # ── Main Loop ──────────────────────────────────────

    async def _run_iteration(self) -> None:
        """Run a complete iteration of the evolutionary pipeline (19 steps).

        ARQ2: Steps are delegated to modular functions in
        backend.orchestrator.steps for maintainability and testability.
        """
        from backend.orchestrator.steps.research_design import (
            run_researcher_step, run_designer_step,
            _prepare_designer_context,
        )
        from backend.orchestrator.steps.develop_build import (
            run_developer_step, run_build_step,
        )
        from backend.orchestrator.steps.analyze_test import (
            run_performance_step, run_headless_test_step,
            run_exploit_step,
            run_sim_analyst_step, run_economy_step, run_tester_step,
        )
        from backend.orchestrator.steps.evaluate_finalize import (
            run_novelty_step, run_quality_step, run_diff_step,
            run_critic_step, run_stagnation_step, run_cost_check_step,
            run_experiment_step, run_memory_curator_step,
        )

        iteration_state = self.state.start_iteration()
        iteration = iteration_state.number

        # v2.2: Update roadmap iteration for deferred task reactivation
        self.roadmap.set_iteration(iteration)

        # v3 Item #12: Start journal capture for this iteration
        self.pipeline_journal.start_iteration(iteration)

        # v2 Roadmap Item 11: Check for runtime model hot-swaps
        try:
            hot_swap = self.model_manager.check_for_updates()
            if hot_swap:
                applied = self.model_manager.apply(self.llm_router, hot_swap)
                self._metrics["model_swaps"] += applied
                await self.emit_chat(
                    "system",
                    f"🔄 Hot-swap: {applied} model override(s) applied",
                    iteration,
                )
        except Exception as exc:
            logger.warning("Model hot-swap check failed: %s", exc)

        # v4: Watchdog tracking
        self.watchdog.record_iteration_start(iteration)
        await self.database.create_iteration(iteration)
        await self._emit("iteration_start", {"iteration": iteration})
        await self.emit_chat(
            "pipeline",
            f"🚀 Iniciando iteração #{iteration}...",
            iteration, "system",
        )

        # Exploration decision (UCB1 controller)
        stag_exploring = self.stagnation_guard.is_exploring
        score_trend = 0.0
        if len(self.state.history) >= 2:
            recent = [h.score for h in self.state.history[-5:]]
            score_trend = recent[-1] - recent[0] if len(recent) >= 2 else 0.0
        exploration_decision = self.exploration_controller.decide(
            is_stagnated=stag_exploring,
            current_score=self.state.best_score,
            score_trend=score_trend,
        )
        exploration = exploration_decision.mode in ("explore", "hybrid")
        perf_score = 50.0
        is_milestone = False

        try:
            # ━━ Step 0: Autonomous Goal Setting (v3 Item #15) ━━━━━━━━
            await self._check_stop_or_pause("goal_setter")
            current_score = float(self.state.best_score)
            if self.goal_setter.should_reevaluate(iteration, current_score):
                await self.emit_chat(
                    "goal_setter",
                    "🎯 Analisando estado do pipeline para definir objetivos...",
                    iteration, "thinking",
                )
                goal_input: dict[str, Any] = {
                    "quality_history": self.quality_engine.get_history()[-10:],
                    "current_gdd": self.designer.current_gdd,
                    "known_bugs": self._known_bugs[:10],
                    "economy_report": self._previous_economy_report,
                    "confidence_stats": self.confidence_scorer.get_stats(),
                    "current_score": current_score,
                }
                try:
                    goal_result = await self.goal_setter.run(iteration, goal_input)
                    if goal_result.success:
                        import json as _json
                        self._last_goals = _json.loads(goal_result.output) if goal_result.output else {}
                        goals_list = self._last_goals.get("goals", [])
                        focus = self._last_goals.get("focus_summary", "")
                        self._metrics["goal_sets_generated"] += 1
                        parts = [f"🎯 {len(goals_list)} objetivo(s) definido(s)"]
                        if focus:
                            parts.append(f"Foco: {focus[:120]}")
                        if goals_list:
                            top = goals_list[0]
                            parts.append(f"Top: [{top.get('area', '?')}] {top.get('description', '')[:80]}")
                        await self.emit_chat("goal_setter", " | ".join(parts), iteration, "success")
                    else:
                        logger.warning("GoalSetter failed: %s", goal_result.error)
                        await self.emit_chat("goal_setter", f"⚠️ Falha ao definir goals: {goal_result.error[:80]}", iteration, "warning")
                except Exception as exc:
                    logger.warning("Goal setter step failed: %s", exc)
            else:
                self._metrics["goal_sets_reused"] += 1
                goals_count = len(self._last_goals.get("goals", []))
                if goals_count:
                    await self.emit_chat(
                        "goal_setter",
                        f"⏭️ Reutilizando {goals_count} objetivo(s) da avaliação anterior",
                        iteration, "system",
                    )

            # ━━ Steps 1–2: Research & Design ━━━━━━━━
            await self._check_stop_or_pause("researcher")

            # Auto-skip: Researcher (too early to research again)
            from backend.core.stale_agent_skipper import StaleAgentSkipper
            _skip_researcher = StaleAgentSkipper.should_skip(
                "researcher", iteration,
            )
            if _skip_researcher and "researcher" in self._last_agent_results:
                self._metrics["tasks_skipped"] += 1
                logger.info("⏭️ Researcher skipped — iteration %d < 3", iteration)
                await self.emit_chat("researcher", "⏭️ Pulado — muito cedo para nova pesquisa", iteration, "system")
                res = self._last_agent_results["researcher"]
                designer_ctx_coro = _prepare_designer_context(self, iteration, exploration)
                designer_pre_ctx = await designer_ctx_coro
            else:
                await self.emit_chat("researcher", "Pesquisando tendências e oportunidades para o jogo...", iteration, "thinking")
                # ⚡ Run researcher + designer context prep in parallel
                researcher_coro = run_researcher_step(self, iteration, exploration)
                designer_ctx_coro = _prepare_designer_context(self, iteration, exploration)
                res, designer_pre_ctx = await asyncio.gather(
                    researcher_coro, designer_ctx_coro,
                )

            researcher_result = res["researcher_result"]
            research_report = res["research_report"]
            proposals = research_report.get("feature_proposals", [])
            focus = research_report.get("recommended_focus", "")
            insights = research_report.get("market_insights", [])
            parts = [f"Pesquisa concluída! {len(proposals)} proposta(s)"]
            if proposals:
                names = [p.get("name", p) if isinstance(p, dict) else str(p) for p in proposals[:3]]
                parts.append("Features: " + ", ".join(names))
            if insights:
                parts.append(f"{len(insights)} insight(s) de mercado")
            if focus:
                parts.append(f"Foco recomendado: {focus[:80]}")
            await self.emit_chat("researcher", " | ".join(parts), iteration, "success")

            await self._check_stop_or_pause("designer")
            await self.emit_chat("designer", "Atualizando o Game Design Document com os insights da pesquisa...", iteration, "thinking")
            des = await run_designer_step(
                self, iteration, exploration, exploration_decision,
                researcher_result, research_report,
                pre_built_context=designer_pre_ctx,
            )
            designer_result = des["designer_result"]
            if not designer_result.success:
                await self.emit_chat("designer", f"❌ Falha no design: {designer_result.error[:100]}", iteration, "error")
                await self._fail_iteration(iteration_state, iteration, designer_result.error)
                return
            gdd_update = des["gdd_update"]
            iteration_state.gdd_update = gdd_update
            if isinstance(gdd_update, dict):
                keys = list(gdd_update.keys())[:5]
                keys_str = ", ".join(keys)
                msg = f"GDD atualizado — {len(gdd_update)} componente(s): {keys_str}"
                if exploration:
                    msg += " [MODO EXPLORAÇÃO]"
            else:
                msg = "GDD atualizado."
            await self.emit_chat("designer", msg, iteration, "success")

            # v3 Item #13: Track GDD evolution
            try:
                gdd_diff = self.gdd_tracker.record(iteration, gdd_update)
                self._metrics["gdd_snapshots_tracked"] += 1
                if gdd_diff and gdd_diff.features_removed:
                    await self.emit_chat(
                        "gdd_tracker",
                        f"⚠️ Features removidas: {', '.join(gdd_diff.features_removed[:3])}",
                        iteration, "warning",
                    )
            except Exception as exc:
                logger.debug("GDD tracking failed: %s", exc)

            # ━━ Steps 3–4: Develop & Build ━━━━━━━━━
            await self._check_stop_or_pause("developer")
            await self.emit_chat("developer", "Escrevendo código baseado no GDD atualizado...", iteration, "thinking")
            dev = await run_developer_step(self, iteration, gdd_update)
            dev_result = dev["dev_result"]
            # When agent forker is used, dev_result is None — the forker
            # returns a MergeResult, not an AgentResult. Treat as success.
            if dev_result is not None and not dev_result.success:
                await self.emit_chat("developer", f"❌ Erro ao escrever código: {dev_result.error[:100]}", iteration, "error")
                await self._fail_iteration(iteration_state, iteration, dev_result.error)
                return
            code_changes = dev["code_changes"]
            iteration_state.code_changes = code_changes
            files_written = (
                dev_result.metadata.get("files_written", [])
                if dev_result is not None
                else [f.get("path", "") for f in code_changes.get("files", []) if isinstance(f, dict)]
            )
            if files_written:
                fnames = [f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for f in files_written[:5]]
                msg = f"Código escrito! {len(files_written)} arquivo(s): {', '.join(fnames)}"
            else:
                msg = "⚠️ Nenhum arquivo gerado nesta iteração."
            await self.emit_chat("developer", msg, iteration, "success")

            # ━━ Pre-Build: v3 Item 10 — Automated Regression Suite ━━━
            regression_result_dict = {}
            try:
                current_src = self.builder.get_source_files()
                self.regression_suite.prune_obsolete(current_src)
                reg_result = self.regression_suite.run_tests(current_src)
                self._metrics["regression_tests_run"] += reg_result.total
                self._metrics["regression_tests_passed"] += reg_result.passed
                regression_result_dict = reg_result.to_dict()
                if not reg_result.is_passing:
                    await self.emit_chat(
                        "regression",
                        f"⚠️ {reg_result.failed} regression test(s) failing!",
                        iteration, "warning",
                    )
                elif reg_result.total > 0:
                    await self.emit_chat(
                        "regression",
                        f"✅ {reg_result.passed}/{reg_result.total} regression tests passing",
                        iteration, "success",
                    )
            except Exception as exc:
                logger.warning("Regression suite pre-build failed: %s", exc)
            # Store for tester_step
            self._regression_result = regression_result_dict

            # ━━ Steps 4 + Async Prep: Build + Analysis Context in PARALLEL ━━━
            await self._check_stop_or_pause("build")
            await self.emit_chat("builder", "Compilando o jogo (lint + build)...", iteration, "thinking")
            await self.emit_chat(
                "pipeline",
                "⚡ Feedback Loop Assíncrono: build + preparação de análise em paralelo...",
                iteration, "thinking",
            )

            # v3 Item 6: Predictive Build Failure (advisory)
            # code_changes is a dict {filename: content}, but build_predictor expects a string
            _code_changes_str = (
                "\n".join(str(v) for v in code_changes.values())
                if isinstance(code_changes, dict) else str(code_changes or "")
            )
            build_prediction = self.build_predictor.predict(
                code_changes=_code_changes_str,
                error_pattern_db=self.error_pattern_db,
                changed_files_count=len(files_written),
                has_new_imports="import " in _code_changes_str,
            )
            self._metrics["build_predictions"] += 1
            if build_prediction.should_review:
                factors_str = ", ".join(build_prediction.risk_factors[:3])
                await self.emit_chat(
                    "builder",
                    f"⚠️ Risco de falha: {build_prediction.failure_probability:.0%} — {factors_str}",
                    iteration, "warning",
                )

            # Launch build and analysis prep concurrently (Item 7)
            build_task = asyncio.create_task(run_build_step(self, iteration, gdd_update))
            prep_task = asyncio.create_task(
                self.analysis_preparer.prepare(iteration, gdd_update, self._previous_files)
            )
            bld, analysis_ctx = await asyncio.gather(build_task, prep_task)
            self._metrics["analysis_prep_parallel"] += 1
            self._metrics["analysis_prep_time_saved_ms"] += int(analysis_ctx.prep_duration_ms)

            build_success = bld["build_success"]
            build_output = bld["build_output"]
            iteration_state.build_success = build_success
            iteration_state.build_output = build_output

            # v3 Item 6: Calibrate predictor with actual result
            self.build_predictor.calibrate(build_succeeded=build_success)

            if build_success:
                await self.emit_chat("builder", "✅ Build passou com sucesso!", iteration, "success")
                self._save_snapshot(iteration)  # score written later by _update_snapshot_score
                # v3 Item 8: Update Semantic Code Graph after successful build
                try:
                    current_src = self.builder.get_source_files()
                    self.code_graph.update(current_src)
                    self._metrics["code_graph_updates"] += 1
                except Exception as exc:
                    logger.warning("Code Graph update failed: %s", exc)
            else:
                await self.emit_chat("builder", f"❌ Build falhou! {build_output[:120]}...", iteration, "error")

                # v2.3 P3: Auto-rollback on build regression (True→False)
                if self._previous_build_success:
                    logger.warning(
                        "⏪ BUILD REGRESSION detected at iter %d! Restoring last good snapshot...",
                        iteration,
                    )
                    await self.emit_chat(
                        "builder",
                        "⏪ Regressão de build detectada — restaurando último snapshot bom...",
                        iteration, "warning",
                    )
                    restored = self._restore_snapshot()
                    if restored:
                        self._metrics.setdefault("build_regressions_fixed", 0)
                        self._metrics["build_regressions_fixed"] += 1
                        # Rebuild after restore
                        _rebuild_ok, _rebuild_out = await self.builder.build()
                        if _rebuild_ok:
                            build_success = True
                            build_output = _rebuild_out
                            iteration_state.build_success = True
                            iteration_state.build_output = _rebuild_out
                            await self.emit_chat(
                                "builder",
                                "✅ Snapshot restaurado e build OK!",
                                iteration, "success",
                            )

            # v2.3 P8: Post-build validation step
            from backend.orchestrator.steps.develop_build import run_post_build_validation
            _validation_warnings = await run_post_build_validation(
                self, iteration, build_success,
            )

            logger.info(
                "⚡ Async prep completed in %.0fms (iter #%d)",
                analysis_ctx.prep_duration_ms, iteration,
            )

            # ━━ Steps 5–11: Analyze & Test (Parallel Batches) ━━━

            # Use pre-computed context from parallel prep
            from backend.core.stale_agent_skipper import StaleAgentSkipper
            changed_files = analysis_ctx.changed_files
            routing_decision = analysis_ctx.routing_decision

            if routing_decision and routing_decision.skipped_agents:
                self._metrics["agents_routed_skipped"] += len(routing_decision.skipped_agents)
                logger.info(
                    "🧭 Agent Router: running %s | skipping %s | %s",
                    sorted(routing_decision.agents_to_run),
                    sorted(routing_decision.skipped_agents),
                    routing_decision.reason,
                )
                await self.emit_chat(
                    "pipeline",
                    f"🧭 Router: {len(routing_decision.agents_to_run)} agentes selecionados "
                    f"({', '.join(sorted(routing_decision.agents_to_run))}) | "
                    f"{routing_decision.reason}",
                    iteration, "system",
                )

            # Emit simulation results from pre-computed context
            sim_aggregate = analysis_ctx.sim_aggregate
            sim_metrics = analysis_ctx.sim_metrics

            # Guard: if analysis prep failed, sim_aggregate may be None
            if sim_aggregate is None:
                from backend.game.simulator import SimulationAggregate
                sim_aggregate = SimulationAggregate()
                sim_metrics = sim_aggregate.to_quality_metrics()
                logger.warning(
                    "⚠️ sim_aggregate is None (analysis prep failed) "
                    "— using fallback defaults for iter #%d", iteration,
                )

            await self._emit("simulation_complete", {
                "iteration": iteration,
                "runs": sim_aggregate.total_runs,
                "crash_rate": sim_aggregate.crash_rate,
                "avg_level": sim_aggregate.avg_level,
                "gold_per_hour": sim_aggregate.avg_gold_per_hour,
                "is_bimodal": sim_aggregate.is_bimodal,
                "confidence_interval": [
                    sim_aggregate.confidence_lower,
                    sim_aggregate.confidence_upper,
                ],
                "per_profile": [
                    {"profile": ps.profile, "avg_level": ps.avg_level}
                    for ps in sim_aggregate.per_profile_stats
                ],
                "retention": {
                    "d1": sim_aggregate.estimated_retention_d1,
                    "d7": sim_aggregate.estimated_retention_d7,
                    "d30": sim_aggregate.estimated_retention_d30,
                },
                "heatmap": sim_aggregate.gameplay_heatmap.to_dict(),
            })

            # ━━ v3 Item 1: Parallel Analysis via DAG Scheduler ━━━━━━━━━

            # Safe defaults — prevent UnboundLocalError if agent is skipped
            # but no cached result exists yet
            prf: dict = {"perf_score": 50, "perf_result": None}
            exp: dict = {}
            eco: dict = {}

            # Determine which agents to skip (pre-computed decisions)
            _skip_perf = analysis_ctx.skip_performance
            if _skip_perf and "performance" in self._last_agent_results:
                prf = self._last_agent_results["performance"]
                self._metrics["tasks_skipped"] += 1
                logger.info("⏭️ Performance Agent skipped — score stable")
                await self.emit_chat("performance", "⏭️ Pulado — score estável desde a última iteração", iteration, "system")
            else:
                _skip_perf = False

            _skip_exploit = analysis_ctx.skip_exploit
            if _skip_exploit and "exploit" in self._last_agent_results:
                exp = self._last_agent_results["exploit"]
                self._metrics["tasks_skipped"] += 1
                logger.info("⏭️ Exploit Detector skipped — sem mudanças de combate/reward")
                await self.emit_chat("exploit_detector", "⏭️ Pulado — sem mudanças em combate/reward", iteration, "system")
            else:
                _skip_exploit = False

            _skip_economy = analysis_ctx.skip_economy
            if _skip_economy and "economy" in self._last_agent_results:
                eco = self._last_agent_results["economy"]
                self._metrics["tasks_skipped"] += 1
                logger.info("⏭️ Economy Guardian skipped — sem mudanças econômicas")
                await self.emit_chat("economy", "⏭️ Pulado — sem mudanças em sistemas econômicos", iteration, "system")
            else:
                _skip_economy = False

            # ── Build analysis DAG with ParallelScheduler ──
            from backend.orchestrator.parallel_scheduler import ParallelScheduler
            analysis_scheduler = ParallelScheduler()

            # Wave 1: performance + headless (independent, both depend on build)
            if not _skip_perf:
                analysis_scheduler.add_step(
                    "performance", set(),
                    lambda: run_performance_step(self, iteration, build_output, build_success, gdd_update),
                )
            analysis_scheduler.add_step(
                "headless", set(),
                lambda: run_headless_test_step(self, iteration, build_success),
            )

            # Wave 1 also: exploit + economy (independent, depend on build + sim already done)
            if not _skip_exploit:
                analysis_scheduler.add_step(
                    "exploit", set(),
                    lambda: run_exploit_step(self, iteration, sim_aggregate),
                )
            if not _skip_economy:
                analysis_scheduler.add_step(
                    "economy", set(),
                    lambda: run_economy_step(self, iteration, sim_metrics, gdd_update),
                )

            # Wave 2: sim_analyst (depends on exploit if it's running)
            sim_analyst_deps: set[str] = set()
            if not _skip_exploit:
                sim_analyst_deps.add("exploit")

            await self._check_stop_or_pause("analysis_parallel")

            dag_info = analysis_scheduler.get_dag_info()
            step_names = dag_info.get("waves", [])
            total_waves = dag_info.get("total_waves", 0)
            total_steps = dag_info.get("total_steps", 0)
            self._metrics["parallel_waves_count"] += total_waves

            await self.emit_chat(
                "pipeline",
                f"🌊 Parallel Scheduler: {total_steps} steps em {total_waves} wave(s) "
                f"({', '.join(s for wave in step_names for s in wave)})",
                iteration, "thinking",
            )

            analysis_results = await analysis_scheduler.execute()

            # ── Extract results from scheduler ──
            if not _skip_perf:
                _perf_raw = analysis_results.get("performance", prf)
                prf = _perf_raw if not isinstance(_perf_raw, dict) or "_error" not in _perf_raw else prf
            hlt = analysis_results.get("headless", {})
            if isinstance(hlt, dict) and "_error" in hlt:
                hlt = {}
            if not _skip_exploit:
                _exp_raw = analysis_results.get("exploit", exp)
                exp = _exp_raw if not isinstance(_exp_raw, dict) or "_error" not in _exp_raw else exp
            if not _skip_economy:
                _eco_raw = analysis_results.get("economy", eco)
                eco = _eco_raw if not isinstance(_eco_raw, dict) or "_error" not in _eco_raw else eco

            # ── Emit performance results ──
            perf_score = prf.get("perf_score", 50)
            perf_result = prf.get("perf_result")
            perf_msg = f"Performance: {perf_score:.0f}/100"
            if perf_result and hasattr(perf_result, "metadata"):
                opt_count = perf_result.metadata.get("optimizations_count", 0)
                if opt_count:
                    perf_msg += f" | {opt_count} otimização(ões) sugerida(s)"
                perf_issues = perf_result.metadata.get("issues", [])
                if perf_issues:
                    top_issues = [str(i)[:60] for i in perf_issues[:2]]
                    perf_msg += " | Problemas: " + "; ".join(top_issues)
            await self.emit_chat("performance", perf_msg, iteration)

            headless_result = hlt.get("headless_result", hlt) if hlt else {}

            # ── Fixer Agent: fix runtime errors detected by headless tester ──
            _hl_console_errors = []
            if isinstance(headless_result, dict):
                _hl_console_errors = headless_result.get("console_errors", [])
            elif hasattr(headless_result, "console_errors"):
                _hl_console_errors = headless_result.console_errors or []

            if _hl_console_errors and build_success:
                logger.info(
                    "🔧 Headless tester found %d console error(s), calling Fixer Agent...",
                    len(_hl_console_errors),
                )
                await self.emit_chat(
                    "fixer",
                    f"🔧 Corrigindo {len(_hl_console_errors)} erro(s) de runtime detectados pelo headless tester...",
                    iteration, "thinking",
                )
                # v2.3 P6: Fixer receives roadmap context
                _fixer_roadmap = self.roadmap.get_developer_context() if hasattr(self, 'roadmap') else ""
                _fixer_rt_input: dict[str, Any] = {
                    "current_files": self.builder.get_source_files(),
                    "console_errors": _hl_console_errors[:20],
                    "roadmap_task": _fixer_roadmap,
                }
                _fixer_rt_result = await self.fixer.run(iteration, _fixer_rt_input)
                if _fixer_rt_result.success:
                    _rt_lint_ok, _rt_lint_out = await self.builder.lint_check()
                    if _rt_lint_ok:
                        _rt_build_ok, _rt_build_out = await self.builder.build()
                        if _rt_build_ok:
                            self._metrics["fixer_runtime_fixes"] += 1
                            logger.info("🔧 Fixer Agent resolved runtime errors!")
                            await self.emit_chat(
                                "fixer",
                                "✅ Runtime errors corrigidos pelo Fixer Agent",
                                iteration, "success",
                            )
                            # Record in error pattern DB
                            for ce in _hl_console_errors[:5]:
                                try:
                                    self.error_pattern_db.record_success(
                                        error_msg=str(ce)[:200],
                                        category="runtime",
                                        fix_description="Fixed runtime error via Fixer Agent",
                                    )
                                except Exception:
                                    pass
                        else:
                            logger.warning("Fixer runtime fix broke build, reverting...")
                    else:
                        logger.warning("Fixer runtime fix failed lint check")

            # ── Fixer Agent: fix rendering issues (game not visible on screen) ──
            _hl_render_failure = False
            if isinstance(headless_result, dict):
                _hl_render_failure = (
                    build_success
                    and headless_result.get("page_loaded", False)
                    and not headless_result.get("game_started", True)
                )
            elif hasattr(headless_result, "game_started"):
                _hl_render_failure = (
                    build_success
                    and getattr(headless_result, "page_loaded", False)
                    and not headless_result.game_started
                )

            if _hl_render_failure:
                _render_diag: list[str] = []
                if isinstance(headless_result, dict):
                    if not headless_result.get("canvas_detected", True):
                        _render_diag.append("Canvas HTML <canvas> NOT detected in page")
                    if not headless_result.get("phaser_detected", True):
                        _render_diag.append("Phaser framework NOT detected (window.Phaser is undefined)")
                    if not headless_result.get("game_started", True):
                        _render_diag.append("Phaser game instance NOT running (Phaser.GAMES is empty or game.isRunning is false)")
                elif hasattr(headless_result, "canvas_detected"):
                    if not headless_result.canvas_detected:
                        _render_diag.append("Canvas HTML <canvas> NOT detected in page")
                    if not headless_result.phaser_detected:
                        _render_diag.append("Phaser framework NOT detected (window.Phaser is undefined)")
                    if not headless_result.game_started:
                        _render_diag.append("Phaser game instance NOT running")

                logger.warning(
                    "🖥️ RENDER FAILURE at iter %d: game not visible! Diagnóstico: %s",
                    iteration, _render_diag,
                )
                await self.emit_chat(
                    "fixer",
                    f"🖥️ Jogo NÃO aparece na tela! {len(_render_diag)} problema(s) de renderização — chamando Fixer...",
                    iteration, "warning",
                )
                _fixer_roadmap_r = self.roadmap.get_developer_context() if hasattr(self, 'roadmap') else ""
                _fixer_render_input: dict[str, Any] = {
                    "current_files": self.builder.get_source_files(),
                    "console_errors": _render_diag + (_hl_console_errors or []),
                    "roadmap_task": _fixer_roadmap_r,
                }
                _fixer_render_result = await self.fixer.run(iteration, _fixer_render_input)
                if _fixer_render_result.success:
                    _rr_lint_ok, _rr_lint_out = await self.builder.lint_check()
                    if _rr_lint_ok:
                        _rr_build_ok, _rr_build_out = await self.builder.build()
                        if _rr_build_ok:
                            self._metrics["fixer_render_fixes"] += 1
                            logger.info("🖥️ Fixer Agent resolved rendering issues!")
                            await self.emit_chat(
                                "fixer",
                                "✅ Correção de renderização aplicada pelo Fixer Agent!",
                                iteration, "success",
                            )
                        else:
                            logger.warning("Fixer render fix broke build, reverting...")
                    else:
                        logger.warning("Fixer render fix failed lint check")
                else:
                    logger.warning("Fixer render fix failed: %s", _fixer_render_result.error)


            # Simulation results from pre-computed context
            sim_parts = [f"Simulação: {sim_aggregate.total_runs} runs"]
            sim_parts.append(f"Nível médio: {sim_aggregate.avg_level:.1f}")
            sim_parts.append(f"Crash rate: {sim_aggregate.crash_rate:.1%}")
            sim_parts.append(f"Retenção D1={sim_aggregate.estimated_retention_d1:.0%} D7={sim_aggregate.estimated_retention_d7:.0%}")
            if sim_aggregate.is_bimodal:
                sim_parts.append("⚠️ Distribuição bimodal detectada")
            await self.emit_chat("simulator", " | ".join(sim_parts), iteration, "success")

            # ── Emit exploit results ──
            exploit_report = exp.get("exploit_report") if exp else None
            if exploit_report is not None and hasattr(exploit_report, "exploit_count"):
                if exploit_report.exploit_count > 0:
                    expl_msg = f"⚠️ {exploit_report.exploit_count} exploit(s) detectado(s)"
                    if exploit_report.has_critical:
                        expl_msg += " — CRÍTICO!"
                    await self.emit_chat("exploit_detector", expl_msg, iteration, "error")
                else:
                    await self.emit_chat("exploit_detector", "✅ Nenhum exploit detectado.", iteration, "success")
            else:
                # Agent was skipped and no cached result — safe fallback
                from backend.core.exploit_detector import ExploitReport
                exploit_report = ExploitReport()
                await self.emit_chat("exploit_detector", "⏭️ Análise de exploits pulada nesta iteração", iteration, "system")

            # ── Emit economy results ──
            economy_report = eco.get("economy_report", {}) if eco else {}
            if economy_report:
                eco_warnings = economy_report.get("warnings", [])
                eco_score = economy_report.get("health_score", economy_report.get("economy_health_score", "?"))
                eco_msg = f"Economia: saúde {eco_score}/100"
                if eco_warnings:
                    eco_msg += f" | ⚠️ {len(eco_warnings)} alerta(s): {str(eco_warnings[0])[:60]}"
                else:
                    eco_msg += " | ✅ Sem alertas"
                await self.emit_chat("economy", eco_msg, iteration, "success")
                # Only update previous report when agent actually ran
                self._previous_economy_report = economy_report
            else:
                economy_report = {"health_score": 50, "warnings": []}
                await self.emit_chat("economy", "⏭️ Análise econômica pulada nesta iteração", iteration, "system")

            # ── sim_analyst (runs after exploit results are available) ──
            await self._check_stop_or_pause("sim_analyst")
            await self.emit_chat("sim_analyst", "Interpretando dados de simulação e exploits...", iteration, "thinking")
            san = await run_sim_analyst_step(self, iteration, sim_metrics, exploit_report, sim_aggregate)
            sim_analysis = san["sim_analysis"]
            sa_insights = len(sim_analysis.get("insights", []))
            sa_actions = len(sim_analysis.get("action_items", []))
            sa_econ = sim_analysis.get("economy_health", {}).get("status", "")
            sa_msg = f"Análise: {sa_insights} insight(s), {sa_actions} ação(ões)"
            if sa_econ:
                sa_msg += f" | Economia: {sa_econ}"
            top_insights = sim_analysis.get("insights", [])[:2]
            if top_insights:
                brief = "; ".join(str(i)[:50] for i in top_insights)
                sa_msg += f" | {brief}"
            await self.emit_chat("sim_analyst", sa_msg, iteration, "success")

            # ── Step 11: tester (needs sim_analysis + economy_report) ──
            await self._check_stop_or_pause("tester")
            await self.emit_chat("tester", "Avaliando qualidade geral do jogo com todos os dados...", iteration, "thinking")
            tst = await run_tester_step(
                self, iteration, build_success, build_output, gdd_update,
                code_changes, sim_aggregate, sim_analysis, economy_report,
            )
            test_report = tst["test_report"]
            eval_metrics = tst["eval_metrics"]
            iteration_state.test_report = test_report
            pe = test_report.get("player_experience", {}) if isinstance(test_report, dict) else {}
            pe_score = pe.get("score", "?")
            bugs = test_report.get("bugs", []) or test_report.get("critical_bugs", []) if isinstance(test_report, dict) else []
            tst_msg = f"Avaliação: experiência do jogador {pe_score}/100"
            if bugs:
                bug_brief = "; ".join(str(b)[:40] for b in bugs[:3])
                tst_msg += f" | 🐛 {len(bugs)} bug(s): {bug_brief}"
            else:
                tst_msg += " | ✅ Sem bugs críticos"
            await self.emit_chat("tester", tst_msg, iteration, "success")

            # ━━ Steps 12–19: Evaluate & Finalize ━━━
            await self._check_stop_or_pause("novelty")
            await self.emit_chat("novelty", "Calculando diversidade e novidade das features...", iteration, "thinking")
            nov = await run_novelty_step(self, iteration, gdd_update)
            novelty_score = nov["novelty_score"]
            await self.emit_chat("novelty", f"Novelty score: {novelty_score:.0f}/100", iteration)

            await self._check_stop_or_pause("quality")
            await self.emit_chat("quality", "Calculando score multi-dimensional de qualidade...", iteration, "thinking")
            qlt = await run_quality_step(
                self, iteration, test_report, sim_metrics,
                eval_metrics, novelty_score, build_success, headless_result,
            )
            quality_breakdown = qlt["quality_breakdown"]
            iteration_state.score = int(quality_breakdown.composite)
            # Snapshot auto-pruning: write score into snapshot metadata
            self._update_snapshot_score(iteration, int(quality_breakdown.composite))
            await self.emit_chat("quality", f"Score final: {quality_breakdown.composite:.0f}/100 (fun={quality_breakdown.fun:.0f}, stab={quality_breakdown.stability:.0f}, bal={quality_breakdown.balance:.0f})", iteration, "success")

            await self._check_stop_or_pause("diff")
            dif = await run_diff_step(self, iteration, iteration_state.score)
            diff_report = dif["diff_report"]
            current_game_files = dif["current_game_files"]
            code_diff = dif["code_diff"]
            iteration_state.score = dif["adjusted_score"]

            await self._check_stop_or_pause("critic")
            await self.emit_chat("critic", "Analisando estrategicamente o progresso e gerando instruções...", iteration, "thinking")
            # v2 Roadmap Item 10: Competitive Benchmark — compare vs genre reference
            benchmark_report: dict[str, Any] | None = None
            try:
                bm_metrics = {
                    "session_length_avg": sim_metrics.get("session_length_avg", 0),
                    "engagement_rate": sim_metrics.get("engagement_rate", 0),
                    "crash_rate_max": sim_metrics.get("crash_rate", 0),
                    "retention_d1": sim_metrics.get("estimated_retention_d1", 0),
                    "retention_d7": sim_metrics.get("estimated_retention_d7", 0),
                    "economy_inflation_max": sim_metrics.get("economy_inflation", 0),
                }
                bm_report = self.benchmark_comparator.compare(bm_metrics, self._config.project.genre)
                benchmark_report = bm_report.to_dict()
                self._metrics["benchmark_comparisons"] += 1
            except Exception as exc:
                logger.warning("Benchmark comparison failed: %s", exc)
            crt = await run_critic_step(
                self, iteration, test_report, gdd_update, quality_breakdown,
                diff_report, sim_aggregate, exploration, dev_result,
                build_success, build_output, current_game_files, perf_score,
                code_diff, benchmark_report,
            )
            critic_feedback = crt["critic_feedback"]
            iteration_state.critic_feedback = critic_feedback
            crt_instr = ""
            crt_priority = ""
            if isinstance(critic_feedback, dict):
                crt_instr = critic_feedback.get("designer_instructions", "")
                crt_priority = critic_feedback.get("priority", critic_feedback.get("focus_area", ""))
            crt_msg = "Análise crítica completa."
            if crt_priority:
                crt_msg += f" Prioridade: {str(crt_priority)[:80]}"
            if crt_instr:
                crt_msg += f" | Instruções: {crt_instr[:120]}"
            await self.emit_chat("critic", crt_msg, iteration, "success")

            await self._check_stop_or_pause("stagnation")
            stg = await run_stagnation_step(self, iteration, quality_breakdown, novelty_score)
            stagnation_result = stg["stagnation_result"]

            await run_cost_check_step(self)

            # ── Store agent results for next-iteration skip logic ──
            self._last_agent_results["researcher"] = res
            self._last_agent_results["performance"] = prf
            self._last_agent_results["exploit"] = exp
            self._last_agent_results["economy"] = eco
            self._last_perf_score = perf_score

            # ━━ FINALIZE ━━━━━━━━━━━━━━━━━━━━━━━━━━━
            self.state.complete_iteration(iteration_state)
            cost_stats = self.cost_guard.get_stats()
            iter_cost = cost_stats.get("total_cost_usd", 0.0)

            self.watchdog.record_iteration_end(iteration, success=True, cost_usd=iter_cost)

            # Save agent memories
            memory_dir = GAME_DIR.parent / "data" / "memory"
            for agent in [self.designer, self.developer, self.tester, self.critic,
                          self.performance_agent, self.researcher, self.simulation_analyst,
                          self.economy_guardian, self.memory_curator]:
                try:
                    agent.memory.save_to_disk(memory_dir)
                except Exception as exc:
                    logger.debug("Could not save memory for %s: %s", agent.name, exc)

            await self.database.update_iteration(
                iteration, status="completed", score=iteration_state.score,
                gdd_snapshot=json.dumps(gdd_update),
                test_report=json.dumps(test_report),
                critic_feedback=json.dumps(critic_feedback),
            )

            # Save snapshot
            is_milestone = iteration_state.score >= self._config.pipeline.quality_threshold

            # v3 Item 10: Generate regression tests at milestones
            if is_milestone:
                try:
                    current_src = self.builder.get_source_files()
                    generated = self.regression_suite.generate_tests(
                        current_src, score=iteration_state.score, iteration=iteration,
                    )
                    self._metrics["regression_tests_generated"] += generated
                    if generated > 0:
                        await self.emit_chat(
                            "regression",
                            f"📋 Generated {generated} new regression test(s) at milestone (score={iteration_state.score})",
                            iteration, "success",
                        )
                except Exception as exc:
                    logger.warning("Regression test generation failed: %s", exc)
            snapshot_path = self.versioner.save_snapshot(
                iteration=iteration, score=iteration_state.score,
                metadata={
                    "is_milestone": is_milestone,
                    "quality_breakdown": {
                        "fun": quality_breakdown.fun, "stability": quality_breakdown.stability,
                        "balance": quality_breakdown.balance, "novelty": quality_breakdown.novelty,
                    },
                    "diff_risk": diff_report.risk_level,
                    "cost_usd": self.cost_guard.get_stats()["total_cost_usd"],
                    "exploration_mode": exploration, "novelty_score": novelty_score,
                },
            )
            await self.database.save_game_version(
                iteration_number=iteration, score=iteration_state.score,
                snapshot_path=snapshot_path, is_milestone=is_milestone,
            )

            # Experiment tracker
            await run_experiment_step(
                self, iteration, quality_breakdown, novelty_score, perf_score,
                sim_aggregate, diff_report, build_success, exploration,
                is_milestone, iteration_state.score, stagnation_result,
            )

            # Memory curator (every 5 iters)
            await run_memory_curator_step(self, iteration)

            # v2 Roadmap Item 9: Self-Reflection (every N iters)
            if self.self_reflection.should_run(iteration):
                try:
                    await self.emit_chat("self_reflection", "Executando meta-análise do pipeline...", iteration, "thinking")
                    self.llm_router.set_context("self_reflection", iteration)
                    sr_input: dict[str, Any] = {
                        "score_history": [h.score for h in self.state.history],
                        "iteration_history": [
                            {"iteration_number": h.number, "score": h.score, "status": h.status}
                            for h in self.state.history[-20:]
                        ],
                        "current_score": iteration_state.score,
                        "total_iterations": iteration,
                    }
                    sr_result = await self.self_reflection.run(iteration, sr_input)
                    if sr_result.success:
                        insights = sr_result.metadata.get("insights", {})
                        summary_text = insights.get("summary", "Meta-análise completa")
                        await self.emit_chat("self_reflection", f"Meta-insights: {str(summary_text)[:300]}", iteration, "success")
                    self._metrics["self_reflections"] += 1
                except Exception as exc:
                    logger.warning("Self-reflection failed: %s", exc)

            # Store experience
            if self.experience_db and self.experience_db.is_available:
                prev_score = self.state.history[-2].score if len(self.state.history) >= 2 else 0
                self.experience_db.store_decision(
                    iteration=iteration, agent="pipeline",
                    action=f"iteration_{iteration}",
                    result=f"score={iteration_state.score}, novelty={novelty_score:.0f}",
                    score_delta=iteration_state.score - prev_score,
                )

            self.exploration_controller.record_outcome(
                strategy=exploration_decision.strategy,
                reward=quality_breakdown.composite / 100.0,
            )

            # v3 Item 7: Record quality for dynamic temperature per agent
            for agent_name in ["designer", "developer", "tester", "critic",
                               "researcher", "performance", "simulation_analyst",
                               "economy_guardian"]:
                self.temperature_controller.record(
                    agent_name, iteration, quality_breakdown.composite,
                )

            # Chat summary
            milestone_tag = " 🏆 MILESTONE!" if is_milestone else ""
            await self.emit_chat(
                "pipeline",
                f"Iteração #{iteration} concluída! Score: {iteration_state.score}/100{milestone_tag}",
                iteration, "success",
            )

            await self._emit("iteration_complete", {
                "iteration": iteration, "score": iteration_state.score,
                "quality": quality_breakdown.composite, "novelty": novelty_score,
                "diff_risk": diff_report.risk_level, "is_milestone": is_milestone,
                "build_success": build_success,
                "cost_usd": self.cost_guard.get_stats()["total_cost_usd"],
                "exploration_mode": exploration,
                "stagnation": stagnation_result.to_dict(),
            })

            # v2.3 P3: Track build success for regression detection next iteration
            self._previous_build_success = build_success

            logger.info(
                "✅ Iter #%d — Score: %d/100 (fun=%.0f stab=%.0f perf=%.0f bal=%.0f nov=%.0f) "
                "| Risk: %s | Cost: $%.4f %s%s",
                iteration, iteration_state.score,
                quality_breakdown.fun, quality_breakdown.stability,
                perf_score, quality_breakdown.balance, quality_breakdown.novelty,
                diff_report.risk_level, self.cost_guard.get_stats()["total_cost_usd"],
                "🏆 MILESTONE!" if is_milestone else "",
                " 🔀 EXPLORING" if exploration else "",
            )

            # v3 Item #12: End journal capture
            self.pipeline_journal.end_iteration(
                iteration,
                final_score=float(iteration_state.score),
                metadata={"build_success": build_success, "exploration": exploration},
            )
            self._metrics["journal_entries"] += 1

        except _PipelineStopRequested as stop_exc:
            logger.info("⛔ Iteração #%d abortada: %s", iteration, stop_exc)
            await self._fail_iteration(iteration_state, iteration, str(stop_exc))
            self.watchdog.record_iteration_end(iteration, success=False, cost_usd=0.0)

        except Exception as exc:
            logger.error("Iteração #%d falhou: %s", iteration, exc)
            await self._fail_iteration(iteration_state, iteration, str(exc))
            self.watchdog.record_iteration_end(iteration, success=False, cost_usd=0.0)
            if self.experience_db and self.experience_db.is_available:
                self.experience_db.store_failure(
                    iteration=iteration, error=str(exc),
                    context=f"Pipeline iteration #{iteration}",
                )
            self.experiment_tracker.record_from_dict(
                iteration=iteration, iteration_status="failed",
                exploration_mode=exploration, tags=["failed"],
            )

    # ── Helpers ────────────────────────────────────────

    async def _build_with_retries(
        self, iteration: int, gdd_update: dict[str, Any],
    ) -> tuple[bool, str]:
        """Build with automatic retry via Developer agent.

        Improvements:
        - Classified errors → targeted fix hints for developer
        - Incremental context → only changed files sent to developer
        - Failed attempt memory → "don't repeat" context
        - Partial merge → restore only broken files from snapshot
        - Build cache → skip build if source unchanged
        """
        from backend.core.build_error_classifier import classify_build_errors, diff_errors

        self._metrics["builds_total"] += 1

        # ── Incremental Build: detect change scope ──
        current_src_files_ib = self.builder.get_source_files()
        build_scope = self.incremental_builder.get_build_scope(current_src_files_ib)

        if not build_scope.has_changes:
            self._metrics["builds_cached"] += 1
            logger.info("⚡ Build cache hit — nenhum arquivo mudou, pulando build")
            return True, "Cached — no changes since last successful build"

        if build_scope.is_full_rebuild:
            self._metrics["incremental_full_rebuilds"] += 1
            logger.info("🔨 Full rebuild: %s", build_scope.reason)
        else:
            self._metrics["incremental_builds"] += 1
            total_files = len(current_src_files_ib)
            skipped = total_files - build_scope.file_count
            self._metrics["incremental_files_skipped"] += skipped
            logger.info(
                "🔨 Incremental build: %d/%d files (%s)",
                build_scope.file_count, total_files, build_scope.reason,
            )

        # Legacy build cache (kept for backward compat)
        current_hash = self._compute_source_hash()

        # ── Pre-flight Import Validator ──
        from backend.core.import_validator import validate_imports
        try:
            pflight_fixed, pflight_fixes = validate_imports(GAME_DIR / "src")
            if pflight_fixed:
                self._metrics["imports_fixed"] += len(pflight_fixes)
                logger.info("🛡️ Pre-flight: %d import(s) corrigidos", len(pflight_fixes))
        except Exception as exc:
            logger.warning("Pre-flight import validator failed: %s", exc)

        # ── Quality Gate: pre-build static analysis ──
        from backend.core.quality_gate import run_quality_gate
        try:
            current_files_for_gate = self.diff_analyzer.get_current_files()
            gate_result = run_quality_gate(current_files_for_gate)
            if not gate_result.passed and gate_result.blocking:
                self._metrics["quality_gate_blocked"] += 1
                logger.warning(
                    "🚧 Quality Gate: %d blocking issues encontradas pré-build",
                    len(gate_result.blocking),
                )
                # Try auto-fix before falling through to Developer
                from backend.core.auto_fixer import try_auto_fix
                error_dicts = [i.to_dict() for i in gate_result.blocking]
                fixed_files, fix_report = try_auto_fix(
                    error_dicts, current_files_for_gate,
                    error_db=self.error_pattern_db,
                )
                if fix_report.any_fixed:
                    self._metrics["auto_fixes_applied"] += fix_report.count
                    # Write fixed files back to disk
                    for fpath, content in fixed_files.items():
                        try:
                            Path(fpath).write_text(content, encoding="utf-8")
                        except Exception:
                            pass
                    logger.info("🔧 Auto-fix: %d correções aplicadas pré-build", fix_report.count)
        except Exception as exc:
            logger.warning("Quality gate check failed: %s", exc)

        lint_ok, lint_output = await self.builder.lint_check()
        if lint_ok:
            build_ok, build_output = await self.builder.build()
            if build_ok:
                self._last_build_hash = current_hash
                self.incremental_builder.update_hashes(current_src_files_ib)
                self._failed_fixes.clear()
                self._last_build_errors = []
                self._metrics["builds_passed"] += 1
                return True, "Lint + build passed"
            lint_output = build_output  # fall through to retry with build errors

        # ── Classify errors for targeted fixes ──
        classification = classify_build_errors(lint_output)
        broken_files = classification.broken_files

        # ── Diff against previous build errors ──
        error_diff = diff_errors(self._last_build_errors, classification.errors)
        self._metrics["errors_diff_computed"] += 1

        # ── Auto-Fix: try rule-based fixes + Error Pattern DB before LLM ──
        from backend.core.auto_fixer import try_auto_fix
        error_dicts = [e.to_dict() for e in classification.errors]
        current_src_files = self.diff_analyzer.get_current_files()
        fixed_files, fix_report = try_auto_fix(
            error_dicts, current_src_files,
            error_db=self.error_pattern_db,
        )
        # Track Error Pattern DB hits
        db_fixes = [f for f in fix_report.fixes if f.rule == "error_db"]
        if db_fixes:
            self._metrics["error_db_hits"] += len(db_fixes)
        if fix_report.any_fixed:
            self._metrics["auto_fixes_applied"] += fix_report.count
            for fpath, content in fixed_files.items():
                try:
                    Path(fpath).write_text(content, encoding="utf-8")
                except Exception:
                    pass
            # Retry build after auto-fix
            re_lint_ok, re_lint_out = await self.builder.lint_check()
            if re_lint_ok:
                re_build_ok, re_build_out = await self.builder.build()
                if re_build_ok:
                    self._last_build_hash = current_hash
                    self.incremental_builder.update_hashes(self.builder.get_source_files())
                    self._failed_fixes.clear()
                    self._last_build_errors = []
                    self._metrics["builds_passed"] += 1
                    self._metrics["auto_fix_builds_saved"] += 1
                    logger.info("🔧 Auto-fix resolveu o build sem LLM!")
                    return True, "Auto-fix resolved build errors"

        last_error_sig = ""
        # Restore only broken files from snapshot (partial merge)
        if broken_files and self._SNAPSHOT_DIR.exists():
            self._partial_restore(broken_files)
        elif self._restore_snapshot():
            logger.info("⏪ Restored full snapshot before build retry")

        for retry in range(self._config.pipeline.max_build_retries):
            await self._check_stop_or_pause(f"build_retry_{retry + 1}")
            self._metrics["retries_total"] += 1

            logger.warning(
                "Build falhou (tentativa %d/%d), pedindo fix ao Fixer Agent...",
                retry + 1, self._config.pipeline.max_build_retries,
            )

            # Skip if identical error repeats
            error_sig = lint_output[:200].strip()
            if error_sig and error_sig == last_error_sig:
                logger.warning("Same build error repeated, skipping remaining retries")
                break
            last_error_sig = error_sig

            # ── Adaptive retry strategy: vary temperature & model tier ──
            strategy = RETRY_STRATEGIES[min(retry, len(RETRY_STRATEGIES) - 1)]
            self.llm_router.set_context(
                "fixer", iteration,
                temperature_override=strategy["temperature"],
                tier_override=strategy["model_tier"],
            )
            if strategy["model_tier"] != "default" or retry > 0:
                self._metrics["retries_adaptive"] += 1
            logger.info(
                "🔧 Fixer retry #%d: temperature=%.1f, tier=%s",
                retry + 1, strategy["temperature"], strategy["model_tier"],
            )

            # ── Incremental context: only changed files (compressed) ──
            from backend.core.prompt_compressor import compress_code_context
            all_files = self.builder.get_source_files()
            changed_files: dict[str, str] = {}
            for fname, content in all_files.items():
                h = hashlib.md5(content.encode()).hexdigest()
                if self._file_hashes.get(fname) != h:
                    changed_files[fname] = content

            compressed_files = compress_code_context(
                changed_files if changed_files else all_files
            )
            self._metrics["prompts_compressed"] += 1

            # ── Build Fixer input with classified errors + memory ──
            fixer_input: dict[str, Any] = {
                "current_files": compressed_files,
                "build_errors": [classification.to_developer_prompt(diff=error_diff) or lint_output[-2000:]],
            }

            # Failed attempt memory: tell Fixer what NOT to try
            if self._failed_fixes:
                fixer_input["failed_fixes"] = [
                    fix.get("summary", "N/A") for fix in self._failed_fixes[-3:]
                ]

            fix_result = await self.fixer.run(iteration, fixer_input)

            if fix_result.success:
                lint_ok, lint_output = await self.builder.lint_check()
                if lint_ok:
                    build_ok, build_output = await self.builder.build()
                    if build_ok:
                        self._last_build_hash = self._compute_source_hash()
                        self._update_file_hashes()
                        self.incremental_builder.update_hashes(self.builder.get_source_files())
                        self._failed_fixes.clear()
                        self._last_build_errors = classification.errors
                        self._metrics["builds_passed"] += 1
                        self._metrics["retries_succeeded"] += 1
                        self._metrics["fixer_fixes"] += 1
                        # Record successful fix in Error Pattern DB for learning
                        for err in classification.errors:
                            try:
                                self.error_pattern_db.record_success(
                                    error_msg=err.message,
                                    category=err.category,
                                    fix_description=f"Fixed by Fixer Agent (retry {retry + 1})",
                                    file=err.file,
                                )
                            except Exception as exc:
                                logger.debug("Error DB record failed: %s", exc)
                        logger.info("🔧 Fixer Agent resolveu o build na tentativa %d!", retry + 1)
                        return True, f"Fixed by Fixer Agent (retry {retry + 1})"
                    lint_output = build_output

                # Re-classify for next retry
                classification = classify_build_errors(lint_output)
                broken_files = classification.broken_files
                error_diff = diff_errors(self._last_build_errors, classification.errors)
                self._metrics["errors_diff_computed"] += 1

            # Record failed attempt
            self._failed_fixes.append({
                "retry": str(retry + 1),
                "error_category": classification.summary or "unknown",
                "summary": f"Fixer retry {retry + 1}: {lint_output[:120]}",
            })

        self.llm_router.clear_overrides()
        self._last_build_errors = classification.errors
        self._metrics["builds_failed"] += 1
        # v3 Item 2: Record failed fixes in Error Pattern DB
        for err in classification.errors:
            try:
                self.error_pattern_db.record_failure(
                    error_msg=err.message,
                    category=err.category,
                )
            except Exception as exc:
                logger.debug("Error DB failure record failed: %s", exc)
        return False, lint_output

    def _compute_source_hash(self) -> str:
        """Compute combined hash of all game source files."""
        from backend.config import GAME_DIR
        src_dir = GAME_DIR / "src"
        if not src_dir.exists():
            return ""
        h = hashlib.md5()
        for f in sorted(src_dir.rglob("*.js")):
            try:
                h.update(f.read_bytes())
            except Exception:
                pass
        return h.hexdigest()

    def _update_file_hashes(self) -> None:
        """Update per-file hash cache after successful build."""
        files = self.builder.get_source_files()
        self._file_hashes = {
            fname: hashlib.md5(content.encode()).hexdigest()
            for fname, content in files.items()
        }

    def _partial_restore(self, broken_files: set[str]) -> None:
        """Restore only the broken files from the latest snapshot."""
        if not self._SNAPSHOT_DIR.exists():
            return
        snapshots = sorted(self._SNAPSHOT_DIR.iterdir(), reverse=True)
        if not snapshots:
            return
        latest = snapshots[0]
        from backend.config import GAME_DIR
        restored = 0
        for bfile in broken_files:
            # Normalize path: "src/systems/Foo.js" → full path
            snap_path = latest / bfile.replace("src/", "", 1) if bfile.startswith("src/") else latest / bfile
            target_path = GAME_DIR / bfile
            if snap_path.exists():
                try:
                    target_path.write_bytes(snap_path.read_bytes())
                    restored += 1
                except Exception:
                    pass
        if restored:
            self._metrics["snapshots_restored"] += 1
            logger.info(
                "🔧 Partial restore: %d/%d broken file(s) restored from snapshot",
                restored, len(broken_files),
            )

    def get_productivity_metrics(self) -> dict[str, Any]:
        """Return pipeline productivity metrics."""
        m = dict(self._metrics)
        total = m["builds_total"] or 1
        m["build_success_rate_pct"] = round(m["builds_passed"] / total * 100, 1)
        m["cache_hit_rate_pct"] = round(m["builds_cached"] / total * 100, 1)
        retries = m["retries_total"] or 1
        m["retry_success_rate_pct"] = round(m["retries_succeeded"] / retries * 100, 1)
        return m

    async def _fail_iteration(
        self, state: Any, iteration: int, error: str,
    ) -> None:
        """Mark an iteration as failed."""
        self.state.fail_iteration(state, error)
        try:
            await self.database.update_iteration(
                iteration, status="failed", error=error[:2000],
            )
        except Exception as exc:
            logger.error(
                "Failed to persist iteration #%d failure: %s", iteration, exc
            )
        # Emit error to chat so dashboard shows what went wrong
        try:
            await self.emit_chat(
                "pipeline",
                f"❌ Iteração #{iteration} falhou: {error[:200]}",
                iteration, "error",
            )
        except Exception:
            pass  # best-effort

    # ── Code Snapshots ─────────────────────────────────

    _SNAPSHOT_DIR = GAME_DIR / ".snapshots"
    _MAX_SNAPSHOTS = 5

    def _save_snapshot(self, iteration: int) -> None:
        """Save a copy of game/src/ after a successful build.

        A ``_score.json`` metadata file is created with the iteration number.
        The actual score is written later by ``_update_snapshot_score`` once
        the quality evaluation completes.
        """
        src_dir = GAME_DIR / "src"
        if not src_dir.exists():
            return
        snap_dir = self._SNAPSHOT_DIR / f"iter_{iteration}"
        try:
            if snap_dir.exists():
                shutil.rmtree(snap_dir)
            shutil.copytree(src_dir, snap_dir)
            # Write initial metadata (score=None until evaluation)
            meta = {"iteration": iteration, "score": None}
            (snap_dir / "_score.json").write_text(json.dumps(meta), encoding="utf-8")
            logger.info("📸 Snapshot saved: iter_%d", iteration)
            self._metrics["snapshots_saved"] += 1
            self._cleanup_old_snapshots()
        except Exception as exc:
            logger.warning("Snapshot save failed: %s", exc)

    def _update_snapshot_score(self, iteration: int, score: int) -> None:
        """Write the final score into a snapshot's metadata file."""
        snap_dir = self._SNAPSHOT_DIR / f"iter_{iteration}"
        meta_file = snap_dir / "_score.json"
        if not snap_dir.exists():
            return
        try:
            meta = {"iteration": iteration, "score": score}
            meta_file.write_text(json.dumps(meta), encoding="utf-8")
            logger.debug("📝 Snapshot score updated: iter_%d → %d", iteration, score)
            # Re-run pruning now that we have score information
            self._cleanup_old_snapshots()
        except Exception as exc:
            logger.warning("Snapshot score update failed: %s", exc)

    def _get_snapshot_score(self, snap_dir: Path) -> int | None:
        """Read the score from a snapshot's ``_score.json``, or *None*."""
        meta_file = snap_dir / "_score.json"
        if not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            return meta.get("score")
        except Exception:
            return None

    def _restore_snapshot(self) -> bool:
        """Restore the most recent snapshot to game/src/."""
        if not self._SNAPSHOT_DIR.exists():
            return False
        snapshots = sorted(self._SNAPSHOT_DIR.iterdir(), reverse=True)
        if not snapshots:
            return False
        latest = snapshots[0]
        src_dir = GAME_DIR / "src"
        try:
            if src_dir.exists():
                shutil.rmtree(src_dir)
            shutil.copytree(latest, src_dir)
            logger.info("⏪ Restored snapshot from %s", latest.name)
            return True
        except Exception as exc:
            logger.warning("Snapshot restore failed: %s", exc)
            return False

    def _cleanup_old_snapshots(self) -> None:
        """Keep only the N best snapshots.

        When the number of snapshots exceeds ``_MAX_SNAPSHOTS``:
        1. Compute the average score of all snapshots that have a score.
        2. Remove the snapshot with the **lowest** score (as long as it is
           below or equal to the average).
        3. If all scores are equal, missing, or no score-based candidate
           exists, fall back to removing the **oldest** snapshot.
        4. The most recent snapshot is **never** removed.
        """
        if not self._SNAPSHOT_DIR.exists():
            return
        snapshots = sorted(self._SNAPSHOT_DIR.iterdir())  # oldest first
        while len(snapshots) > self._MAX_SNAPSHOTS:
            latest = snapshots[-1]  # never remove the most recent

            # Gather scores
            scored: list[tuple[Path, int]] = []
            for s in snapshots:
                sc = self._get_snapshot_score(s)
                if sc is not None:
                    scored.append((s, sc))

            victim: Path | None = None
            if scored:
                avg = sum(sc for _, sc in scored) / len(scored)
                # Candidates: below-or-equal average and not the latest
                candidates = [
                    (s, sc) for s, sc in scored
                    if sc <= avg and s != latest
                ]
                if candidates:
                    # Pick the one with lowest score (tie-break: oldest)
                    candidates.sort(key=lambda x: (x[1], x[0].name))
                    victim = candidates[0][0]

            # Fallback: oldest snapshot (that isn't the latest)
            if victim is None:
                for s in snapshots:
                    if s != latest:
                        victim = s
                        break

            if victim is None:
                break  # safety: only 1 snapshot left

            try:
                shutil.rmtree(victim)
                snapshots.remove(victim)
                self._metrics["snapshots_pruned"] += 1
                logger.info(
                    "🗑️ Snapshot pruned: %s (score=%s)",
                    victim.name,
                    self._get_snapshot_score(victim) if victim.exists() else "removed",
                )
            except Exception:
                snapshots.remove(victim)  # avoid infinite loop
