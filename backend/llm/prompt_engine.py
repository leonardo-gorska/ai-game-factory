"""
GORVAX GAME FACTORY — Prompt Engine
Renders agent prompt templates with dynamic project configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.config import (
    ProjectConfig,
    PROMPTS_DIR,
)

if TYPE_CHECKING:
    from backend.llm.prompt_optimizer import PromptOptimizer

logger = logging.getLogger(__name__)

# ── Genre-specific mechanics (injected into designer prompt) ──

GENRE_MECHANICS: dict[str, str] = {
    "idle_rpg": (
        "- **Idle Loop**: Auto-combat, auto-loot, offline progression\n"
        "- **Hero System**: Classes, stats, skills, levels, equipment\n"
        "- **Combat System**: Turn-based auto-combat with strategic depth\n"
        "- **Progression**: XP curves, gold economy, gem (premium currency) balance\n"
        "- **Content**: Dungeons, enemies, bosses, items, skills\n"
        "- **UI/UX**: Screen layouts, information hierarchy, player flow"
    ),
    "action": (
        "- **Action Loop**: Real-time combat, player movement, abilities\n"
        "- **Character System**: Stats, skills, upgrades, unlockables\n"
        "- **Combat System**: Real-time action with dodge, attack, combo mechanics\n"
        "- **Level Design**: Stages, waves, difficulty scaling\n"
        "- **Scoring**: Points, multipliers, leaderboards\n"
        "- **UI/UX**: HUD, health bars, ability cooldowns"
    ),
    "puzzle": (
        "- **Puzzle Loop**: Level-based challenges, increasing difficulty\n"
        "- **Mechanics**: Match-3, tile swapping, logic puzzles, or physics puzzles\n"
        "- **Scoring**: Stars, time limits, move limits\n"
        "- **Progression**: Unlock new worlds/chapters, hint system\n"
        "- **Power-ups**: Special abilities, boosters\n"
        "- **UI/UX**: Clean grid, animations, particle effects"
    ),
    "tower_defense": (
        "- **TD Loop**: Place towers, start waves, upgrade defenses\n"
        "- **Tower System**: Types (archer, mage, cannon), upgrades, synergies\n"
        "- **Enemy System**: Waves, paths, enemy types (fast, tanky, flying)\n"
        "- **Economy**: Gold per kill, tower costs, upgrade costs\n"
        "- **Map Design**: Paths, choke points, buildable areas\n"
        "- **UI/UX**: Tower placement, wave info, resource counters"
    ),
    "platformer": (
        "- **Movement**: Run, jump, wall-jump, dash\n"
        "- **Level Design**: Platforms, obstacles, collectibles, secrets\n"
        "- **Enemy System**: Patrol AI, jump-on-head, shooting\n"
        "- **Progression**: Levels, worlds, unlockable abilities\n"
        "- **Collectibles**: Coins, stars, power-ups\n"
        "- **UI/UX**: Responsive controls, camera follow, parallax scrolling"
    ),
    "racing": (
        "- **Racing Loop**: Tracks, laps, time trials, tournaments\n"
        "- **Vehicle System**: Speed, acceleration, handling, upgrades\n"
        "- **Track Design**: Curves, obstacles, shortcuts, hazards\n"
        "- **Progression**: Unlock cars, tracks, customization\n"
        "- **AI Opponents**: Rubber-banding, difficulty levels\n"
        "- **UI/UX**: Speedometer, minimap, position indicator"
    ),
    "roguelike": (
        "- **Core Loop**: Procedural dungeon runs, permadeath, meta-progression\n"
        "- **Map Generation**: Random room layouts, corridors, traps, treasures\n"
        "- **Combat**: Turn-based or real-time, diverse enemy types and patterns\n"
        "- **Items & Synergies**: Randomized loot, item combos, build diversity\n"
        "- **Progression**: Unlockable characters, starting items, difficulty tiers\n"
        "- **UI/UX**: Minimap, inventory management, run statistics"
    ),
    "survival": (
        "- **Survival Loop**: Gather resources, craft, build shelter, survive\n"
        "- **Resource System**: Hunger, thirst, health, stamina, temperature\n"
        "- **Crafting**: Recipes, workbenches, tool progression\n"
        "- **World**: Day/night cycle, weather, biomes, wildlife\n"
        "- **Threats**: Enemies, environmental hazards, decay\n"
        "- **UI/UX**: Inventory, crafting menu, status bars, map"
    ),
    "strategy": (
        "- **Strategy Loop**: Build base, manage resources, command units\n"
        "- **Economy**: Resource gathering, production chains, trading\n"
        "- **Units**: Types (melee, ranged, siege), upgrades, formations\n"
        "- **Buildings**: Production, defense, research, storage\n"
        "- **AI Opponents**: Difficulty scaling, strategic behavior\n"
        "- **UI/UX**: Top-down view, minimap, unit selection, resource HUD"
    ),
    "simulation": (
        "- **Sim Loop**: Manage systems, balance inputs/outputs, grow\n"
        "- **Systems**: Economy, population, happiness, environment\n"
        "- **Building**: Placement, zoning, upgrades, specialization\n"
        "- **Events**: Random events, disasters, opportunities, milestones\n"
        "- **Progression**: Unlock tiers, new buildings, achievements\n"
        "- **UI/UX**: Overview dashboards, graphs, notifications, overlays"
    ),
}

# ── Monetization strategy descriptions (injected into all agent prompts) ──

MONETIZATION_STRATEGIES: dict[str, str] = {
    "free_with_ads": (
        "**Modelo: Grátis + Anúncios**\n"
        "- Rewarded video ads para recompensas opcionais (2x gold, revive, bonus chest)\n"
        "- Interstitial ads entre sessões/levels (máximo 1 a cada 3 minutos)\n"
        "- Banner ads opcional em telas de menu (NUNCA durante gameplay ativo)\n"
        "- SEM compras in-app — toda monetização vem de ads\n"
        "- Prioridade: maximizar sessões longas e retenção para mais impressões\n"
        "- Regra: ads NUNCA devem interromper o flow do jogador"
    ),
    "freemium": (
        "**Modelo: Freemium (IAP)**\n"
        "- Compras in-app: moeda premium, battle pass, cosmetics, boosters\n"
        "- SEM anúncios — experiência limpa\n"
        "- Dual currency: soft currency (grindable) + hard currency (comprável)\n"
        "- Starter packs, bundles sazonais, ofertas limitadas\n"
        "- Prioridade: conversão de free-to-pay (meta: 2-5% dos jogadores)\n"
        "- Regra: jogadores free devem progredir, apenas mais devagar"
    ),
    "hybrid": (
        "**Modelo: Híbrido (Ads + IAP)**\n"
        "- Rewarded video ads para recompensas menores\n"
        "- Compras in-app para conteúdo premium e progressão\n"
        "- Remove-ads como IAP premium (~$2.99-$4.99)\n"
        "- Jogadores que pagam = sem ads; free players = ads opcionais\n"
        "- Prioridade: maximizar ARPDAU via ambos os canais\n"
        "- Regra: ads são alternativa, não punição — oferecer escolha"
    ),
    "premium": (
        "**Modelo: Premium (Pago)**\n"
        "- Jogo pago ($0.99-$9.99), acesso completo imediato\n"
        "- SEM anúncios, SEM compras in-app\n"
        "- Todo conteúdo desbloqueável por gameplay\n"
        "- Prioridade: valor percebido alto — demo/trailer/screenshots impactantes\n"
        "- Expansões/DLC opcionais para conteúdo adicional\n"
        "- Regra: experiência completa e polida desde o primeiro segundo"
    ),
    "none": (
        "**Modelo: Sem Monetização**\n"
        "- Jogo 100% gratuito, sem ads, sem compras\n"
        "- Foco exclusivo em gameplay e diversão\n"
        "- Ideal para portfolio, jam, educação ou hobby\n"
        "- NÃO desenhar hooks de monetização\n"
        "- Prioridade: experiência do jogador pura\n"
        "- Regra: nenhum design deve ser influenciado por monetização"
    ),
}

# ── Engine-specific tech stack info (injected into developer prompt) ──

ENGINE_FEATURES: dict[str, str] = {
    "phaser3": (
        "- **Engine**: Phaser 3 (latest)\n"
        "- **Build**: Vite\n"
        "- **Language**: JavaScript (ES modules)\n"
        "- **Structure**: Scene-based architecture with modular systems"
    ),
    "pixijs": (
        "- **Engine**: Pixi.js v7+\n"
        "- **Build**: Vite\n"
        "- **Language**: JavaScript (ES modules)\n"
        "- **Structure**: Application + Container hierarchy with Ticker for game loop"
    ),
    "threejs": (
        "- **Engine**: Three.js (latest)\n"
        "- **Build**: Vite\n"
        "- **Language**: JavaScript (ES modules)\n"
        "- **Structure**: Scene + Camera + Renderer with requestAnimationFrame loop"
    ),
    "canvas": (
        "- **Engine**: HTML5 Canvas 2D API (native)\n"
        "- **Build**: Vite\n"
        "- **Language**: JavaScript (ES modules)\n"
        "- **Structure**: Custom game loop with requestAnimationFrame, modular systems"
    ),
    "unity": (
        "- **Engine**: Unity (WebGL export)\n"
        "- **Build**: Unity Build Pipeline → WebGL\n"
        "- **Language**: C# (Unity scripting)\n"
        "- **Structure**: GameObject + MonoBehaviour architecture, Unity Editor workflow"
    ),
    "godot": (
        "- **Engine**: Godot 4.x (HTML5 export)\n"
        "- **Build**: Godot Export Templates → HTML5/WebAssembly\n"
        "- **Language**: GDScript or C#\n"
        "- **Structure**: Node tree with scene composition, signals for communication"
    ),
    "unreal": (
        "- **Engine**: Unreal Engine 5 (Pixel Streaming)\n"
        "- **Build**: Unreal Build Tool → Pixel Streaming server\n"
        "- **Language**: C++ / Blueprints\n"
        "- **Structure**: Actor + Component system, Level-based, heavy asset pipeline"
    ),
}


class PromptEngine:
    """
    Loads prompt templates from disk and renders them with project-specific
    variables (game name, engine, genre, platform).

    Optionally integrates with PromptOptimizer for adaptive prompt tuning
    (Roadmap v3 Item #3).
    """

    def __init__(
        self,
        project_config: ProjectConfig | None = None,
        optimizer: PromptOptimizer | None = None,
    ) -> None:
        self.project = project_config or ProjectConfig()
        self.optimizer = optimizer
        self._cache: dict[str, str] = {}
        # v3 Item #14: Inject confidence scoring instruction into prompts
        self._inject_confidence = True

    def update_project(self, project_config: ProjectConfig) -> None:
        """Update the project config and clear the template cache."""
        self.project = project_config
        self._cache.clear()

    def render(self, template_name: str) -> str:
        """
        Load and render a prompt template.

        Args:
            template_name: Name without extension (e.g. 'designer', 'developer')

        Returns:
            Rendered prompt string with all placeholders replaced.
        """
        cache_key = f"{template_name}:{self.project.game_name}:{self.project.engine}:{self.project.genre}:{self.project.monetization}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try .md first, then .txt
        template_path = PROMPTS_DIR / f"{template_name}.md"
        if not template_path.exists():
            template_path = PROMPTS_DIR / f"{template_name}.txt"
        if not template_path.exists():
            logger.warning("Prompt template not found: %s", template_name)
            return ""

        raw = template_path.read_text(encoding="utf-8")

        # Build replacement variables
        vars_ = self.project.to_prompt_vars()

        # B1: Only inject genre_mechanics for designer/developer agents
        if template_name in ("designer", "developer"):
            genre_mech = GENRE_MECHANICS.get(self.project.genre)
            if genre_mech is None:
                logger.warning(
                    "CFG-03: No GENRE_MECHANICS entry for '%s', falling back to idle_rpg",
                    self.project.genre,
                )
                genre_mech = GENRE_MECHANICS["idle_rpg"]
            vars_["genre_mechanics"] = genre_mech
        else:
            vars_["genre_mechanics"] = ""

        # B1: Only inject monetization when relevant
        monetization = getattr(self.project, "monetization", "none")
        if monetization != "none":
            vars_["monetization_strategy"] = MONETIZATION_STRATEGIES.get(
                monetization, ""
            )
        else:
            vars_["monetization_strategy"] = ""

        engine_feat = ENGINE_FEATURES.get(self.project.engine)
        if engine_feat is None:
            logger.warning(
                "CFG-03: No ENGINE_FEATURES entry for '%s', falling back to phaser3",
                self.project.engine,
            )
            engine_feat = ENGINE_FEATURES["phaser3"]
        vars_["engine_features"] = engine_feat

        # Apply replacements using safe string formatting
        rendered = raw
        for key, value in vars_.items():
            rendered = rendered.replace(f"{{{key}}}", value)

        self._cache[cache_key] = rendered

        # v3 Item #14: Append confidence instruction
        if self._inject_confidence:
            rendered += (
                '\n\nIMPORTANT: In your JSON response, include a '
                '"confidence" field with a value from 0 to 100 '
                'indicating how confident you are in the quality '
                'and correctness of your output.'
            )

        return rendered

    def render_with_variant(
        self,
        template_name: str,
        agent_name: str,
    ) -> tuple[str, str, float]:
        """
        Render a prompt with adaptive variant suggestion.

        If an optimizer is configured and has enough data, it suggests
        the best temperature for this agent. Otherwise, returns defaults.

        Args:
            template_name: Prompt template name.
            agent_name: Agent requesting the prompt.

        Returns:
            Tuple of (rendered_prompt, prompt_hash, suggested_temperature).
        """
        from backend.llm.prompt_optimizer import compute_prompt_hash

        rendered = self.render(template_name)
        prompt_hash = compute_prompt_hash(rendered)
        suggested_temp = 0.7  # default

        if self.optimizer:
            suggestion = self.optimizer.suggest_variant(agent_name)
            suggested_temp = suggestion.temperature
            logger.debug(
                "📊 PromptEngine: variant for %s → temp=%.2f (%s)",
                agent_name,
                suggestion.temperature,
                suggestion.variant_id,
            )

        return rendered, prompt_hash, suggested_temp

    def render_all(self) -> dict[str, str]:
        """Render all available prompt templates."""
        results: dict[str, str] = {}
        for path in PROMPTS_DIR.iterdir():
            if path.suffix in (".md", ".txt"):
                name = path.stem
                results[name] = self.render(name)
        return results
