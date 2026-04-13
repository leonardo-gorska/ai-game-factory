"""
GORVAX GAME FACTORY — Developer Agent
Writes and modifies game code based on the GDD.
"""

from __future__ import annotations

import json
import shutil
from backend.utils.json_parser import extract_json_from_response
import logging
from pathlib import Path
from typing import Any

from backend.agents.result_types import DeveloperMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR, GAME_DIR, load_project_config

logger = logging.getLogger(__name__)

# Maximum number of parse retries before giving up
_MAX_PARSE_RETRIES = 1


class DeveloperAgent(BaseAgent):
    """
    The Game Developer agent. Writes JavaScript game code
    based on the Game Design Document from the Designer agent.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "developer.md").read_text(encoding="utf-8")
        super().__init__(
            name="developer",
            role="Game Developer",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Generate or modify game code based on the GDD.

        input_data should contain:
          - gdd_update: dict (from Designer agent)
          - current_files: dict[str, str] (current game source files)
          - build_errors: list[str] (if retrying after build failure)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.4,  # Lower temperature for code
                max_tokens=16384,  # Increased for complete code generation
                json_mode=True,  # Request JSON output from LLM
            )

            code_changes = self._parse_code_response(response)
            files_list = code_changes.get("files", [])

            # ── Retry if no files were produced ──────────────────
            if not files_list and not input_data.get("build_errors"):
                logger.warning(
                    "Developer produced 0 files on iteration %d. "
                    "Response length=%d. Retrying with explicit JSON instruction...",
                    iteration, len(response),
                )
                # Log a snippet of the response for debugging
                logger.debug(
                    "Failed response preview: %s",
                    response[:500],
                )

                # Retry with a very explicit prompt asking for JSON
                retry_response = await self._call_llm(
                    prompt=self._build_retry_prompt(response),
                    context="",
                    temperature=0.2,  # Even lower temp for retry
                    max_tokens=16384,
                    json_mode=True,
                )
                code_changes = self._parse_code_response(retry_response)
                files_list = code_changes.get("files", [])

                if files_list:
                    logger.info(
                        "Retry succeeded: got %d file(s) on iteration %d",
                        len(files_list), iteration,
                    )
                else:
                    logger.error(
                        "Developer retry also produced 0 files on iteration %d. "
                        "Pipeline iteration will be degraded.",
                        iteration,
                    )

            # Ensure scaffold exists before writing (copies fixed templates on first run)
            self._ensure_scaffold()

            files_written = await self._write_files(code_changes)

            if files_written:
                logger.info(
                    "✅ Developer wrote %d file(s) on iteration %d: %s",
                    len(files_written), iteration,
                    ", ".join(files_written[:5]),
                )
            else:
                logger.warning(
                    "⚠️ Developer wrote 0 files on iteration %d",
                    iteration,
                )

            metadata: DeveloperMetadata = {
                "code_changes": code_changes,
                "files_written": files_written,
            }
            return AgentResult(
                agent_name=self.name,
                action="write_code",
                output=json.dumps({
                    "summary": code_changes.get("summary", "Code updated"),
                    "files_modified": files_written,
                }),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Developer failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="write_code",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        parts: list[str] = []

        # Inject roadmap task context FIRST — this is the primary directive
        roadmap_task = input_data.get("roadmap_task", "")
        if roadmap_task:
            parts.append(f"{roadmap_task}\n")

        if iteration == 1:
            game_name = load_project_config().game_name
            parts.append(
                f"Create the initial game code for {game_name} based on this GDD.\n"
                "Build the complete scaffold with all files listed in the project structure.\n"
                "The game should boot, show a basic main scene, and have working idle gold generation.\n"
            )

        # Include GDD update
        gdd = input_data.get("gdd_update", {})
        if gdd:
            gdd_text = json.dumps(gdd, indent=2) if isinstance(gdd, dict) else str(gdd)
            parts.append(f"## Game Design Document Update\n```json\n{gdd_text}\n```\n")

        # Include current files for context
        current_files = input_data.get("current_files", {})
        if current_files:
            files_context = []
            # Critical files get full context; others are truncated
            CRITICAL_FILES = {"config.js", "MainScene.js"}
            for path, content in current_files.items():
                fname = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                limit = 8000 if fname in CRITICAL_FILES else 3000
                truncated = content[:limit] + "..." if len(content) > limit else content
                files_context.append(f"### {path}\n```javascript\n{truncated}\n```")
            parts.append(f"## Current Game Files\n{''.join(files_context)}\n")

        # Include build errors if retrying
        build_errors = input_data.get("build_errors", [])
        if build_errors:
            errors_text = "\n".join(f"- {e}" for e in build_errors)
            parts.append(
                f"## ⚠️ BUILD ERRORS — Fix These!\n{errors_text}\n"
                "The previous build failed. Fix these errors while keeping all other code working.\n"
            )

        # P4: Inject accumulated context from previous iterations
        test_report = input_data.get("last_test_report", {})
        if test_report and isinstance(test_report, dict):
            report_text = json.dumps(test_report, indent=2)[:2000]
            parts.append(
                f"## ⚠️ Previous Test Report (address these issues)\n```json\n{report_text}\n```\n"
            )

        critic_feedback = input_data.get("last_critic_feedback", {})
        if critic_feedback and isinstance(critic_feedback, dict):
            feedback_text = json.dumps(critic_feedback, indent=2)[:2000]
            parts.append(
                f"## 🎯 Critic Priorities (focus on these)\n```json\n{feedback_text}\n```\n"
            )

        quality_info = input_data.get("quality_breakdown", {})
        if quality_info and isinstance(quality_info, dict):
            parts.append(
                f"## 📊 Current Quality Scores\n"
                f"- Fun: {quality_info.get('fun', '?')}/100\n"
                f"- Stability: {quality_info.get('stability', '?')}/100\n"
                f"- Balance: {quality_info.get('balance', '?')}/100\n"
                f"- Performance: {quality_info.get('performance', '?')}/100\n"
                f"Focus on improving the LOWEST scores.\n"
            )

        known_bugs = input_data.get("known_bugs", [])
        if known_bugs:
            bugs_text = "\n".join(f"- {b}" for b in known_bugs[-10:])
            parts.append(
                f"## 🐛 Known Bugs (DO NOT reintroduce these)\n{bugs_text}\n"
            )

        # v3 Item 8: Semantic Code Graph — dependent files context
        dependency_context = input_data.get("dependency_context", {})
        if dependency_context and isinstance(dependency_context, dict):
            dep_parts = []
            for dep_path, dep_content in dependency_context.items():
                truncated = dep_content[:2000] + "..." if len(dep_content) > 2000 else dep_content
                dep_parts.append(f"### {dep_path}\n```javascript\n{truncated}\n```")
            parts.append(
                "## ⚠️ Dependent Files (these import files you may change — avoid breaking them)\n"
                + "\n".join(dep_parts) + "\n"
            )

        parts.append(
            "Respond with the complete file contents in the specified JSON format.\n"
            "Include ALL files that need to be created or modified.\n"
            "ONLY create/modify files for the current task — do NOT rewrite existing files.\n\n"
            "REMINDER: Your response MUST be a single valid JSON object with this structure:\n"
            '{"summary": "...", "files": [{"path": "src/...", "action": "create", "content": "..."}]}'
        )

        return "\n\n".join(parts)

    def _build_retry_prompt(self, failed_response: str) -> str:
        """Build a retry prompt when the first response didn't produce valid JSON."""
        return (
            "Your previous response could not be parsed as valid JSON.\n\n"
            "You MUST respond with ONLY a valid JSON object. No text before or after.\n"
            "No markdown, no explanations, just the JSON.\n\n"
            "Required format:\n"
            "```json\n"
            "{\n"
            '  "summary": "Brief description",\n'
            '  "files": [\n'
            '    {"path": "src/main.js", "action": "create", "content": "// full file content"}\n'
            "  ]\n"
            "}\n"
            "```\n\n"
            "Here is your previous response. Convert it to the JSON format above:\n\n"
            f"{failed_response[:8000]}"
        )

    def _parse_code_response(self, response: str) -> dict[str, Any]:
        """Extract code changes JSON from the LLM response."""
        return extract_json_from_response(response, fallback={
            "summary": "Code generation (raw response)",
            "files": [],
            "raw_response": response[:1000],
        })

    @staticmethod
    def _ensure_scaffold() -> None:
        """Copy fixed scaffold files (main.js, BootScene.js) if they don't exist yet.

        This guarantees infrastructure files are always correct, regardless
        of LLM output. Called before _write_files on every iteration, but
        only copies when the target file is missing.
        """
        scaffold_dir = Path(__file__).parent.parent / "templates" / "scaffold"
        if not scaffold_dir.exists():
            return

        targets = {
            "main.js": GAME_DIR / "src" / "main.js",
            "BootScene.js": GAME_DIR / "src" / "scenes" / "BootScene.js",
        }

        for template_name, target_path in targets.items():
            if target_path.exists():
                continue
            source = scaffold_dir / template_name
            if not source.exists():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)
            logger.info("📦 Scaffold: copied %s → %s", template_name, target_path.relative_to(GAME_DIR))

    async def _write_files(self, code_changes: dict[str, Any]) -> list[str]:
        """Write code files to the game directory."""
        files_written: list[str] = []
        game_src = GAME_DIR / "src"

        for file_entry in code_changes.get("files", []):
            file_path = file_entry.get("path", "")
            action = file_entry.get("action", "create")
            content = file_entry.get("content", "")

            if not file_path or not content:
                continue

            # Block LLM from overwriting project infrastructure files
            basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            BLOCKED_FILES = {"vite.config.js", "package.json", "index.html", ".eslintrc.js", ".eslintrc.json", "main.js", "BootScene.js", "game.js", "game_config.json"}

            # Smart merge for config.js — allow ADDING new constants, block removing existing
            if basename == "config.js":
                config_path = GAME_DIR / "src" / "config.js"
                if config_path.exists():
                    existing = config_path.read_text(encoding="utf-8")
                    merged = self._smart_merge_config(existing, content)
                    if merged != existing:
                        config_path.write_text(merged, encoding="utf-8")
                        files_written.append(str(config_path.relative_to(GAME_DIR)))
                        logger.info("🔀 Smart-merged config.js (%d new lines)", merged.count('\n') - existing.count('\n'))
                    else:
                        logger.info("🛡️ config.js unchanged after smart merge — skipping")
                else:
                    # First time — write normally
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    config_path.write_text(content, encoding="utf-8")
                    files_written.append(str(config_path.relative_to(GAME_DIR)))
                continue

            # Smart merge for MainScene.js — preserve existing imports and create() body
            if basename == "MainScene.js":
                scene_path = GAME_DIR / "src" / "scenes" / "MainScene.js"
                if scene_path.exists():
                    existing = scene_path.read_text(encoding="utf-8")
                    merged = self._smart_merge_scene(existing, content)
                    content = self._validate_js_brackets(merged, file_path)
                    scene_path.write_text(content, encoding="utf-8")
                    files_written.append(str(scene_path.relative_to(GAME_DIR)))
                    logger.info(
                        "🔀 Smart-merged MainScene.js (preserved existing + added new)"
                    )
                    continue
                # else: first time — fall through to normal write

            if basename in BLOCKED_FILES:
                logger.warning("🛡️ Blocked write to infrastructure file: %s", file_path)
                continue

            # Normalize path — ensure it's relative to game/
            if file_path.startswith("src/"):
                full_path = GAME_DIR / file_path
            elif file_path.startswith("game/src/"):
                full_path = GAME_DIR / file_path.replace("game/", "", 1)
            else:
                full_path = game_src / file_path

            # SEC-03: Block path traversal — ensure file stays inside GAME_DIR
            resolved = full_path.resolve()
            game_resolved = GAME_DIR.resolve()
            if not str(resolved).startswith(str(game_resolved)):
                logger.warning("🛡️ Path traversal blocked: %s → %s", file_path, resolved)
                continue

            if action == "delete":
                if full_path.exists():
                    full_path.unlink()
                    files_written.append(f"DELETED: {file_path}")
                continue

            # Create directory if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Post-process config.js: auto-add 'export' to bare 'const' declarations
            if basename == "config.js":
                import re
                # Add 'export' to lines that start with 'const ' but not 'export const'
                content = re.sub(
                    r'^(const\s)',
                    r'export \1',
                    content,
                    flags=re.MULTILINE
                )
                logger.info("🔧 Auto-fixed config.js: ensured all const declarations are exported")

            # Validate JS bracket balance before writing
            content = self._validate_js_brackets(content, file_path)

            # Write the file
            full_path.write_text(content, encoding="utf-8")
            files_written.append(str(file_path))
            logger.info("Wrote game file: %s (%d bytes)", full_path, len(content))

        # Pre-flight: validate all imports resolve to real files
        self._preflight_check_imports()

        return files_written

    @staticmethod
    def _smart_merge_config(existing: str, new_content: str) -> str:
        """Merge config.js: keep existing constants, add new ones only.

        Handles multi-line declarations like:
            export const SOUNDS = {
              HIT: 'hit',
            };
        """
        import re

        # Extract existing constant names
        existing_names: set[str] = set()
        for match in re.finditer(r'export\s+const\s+(\w+)', existing):
            existing_names.add(match.group(1))

        # Parse new_content into complete declaration blocks
        new_blocks: list[str] = []
        lines = new_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r'export\s+const\s+(\w+)', line)
            if m and m.group(1) not in existing_names:
                # Start of a new export block — capture the full declaration
                block_lines = [line]
                # Check if the declaration opens a brace/bracket
                open_braces = line.count('{') - line.count('}')
                open_brackets = line.count('[') - line.count(']')
                i += 1
                # Keep capturing lines until braces/brackets are balanced
                while i < len(lines) and (open_braces > 0 or open_brackets > 0):
                    block_lines.append(lines[i])
                    open_braces += lines[i].count('{') - lines[i].count('}')
                    open_brackets += lines[i].count('[') - lines[i].count(']')
                    i += 1
                new_blocks.append('\n'.join(block_lines))
            else:
                i += 1

        if not new_blocks:
            return existing

        # Append new constants at the end
        result = existing.rstrip()
        result += '\n\n// ── Auto-added by roadmap ──\n'
        result += '\n\n'.join(new_blocks) + '\n'
        return result

    @staticmethod
    def _smart_merge_scene(existing: str, new_content: str) -> str:
        """Merge MainScene.js: keep existing imports and create() body, add new ones.

        Strategy:
        1. Extract all import lines from both existing and new content
        2. Merge import lines (union), preserving order from existing + new at end
        3. For the class body, use the new content BUT ensure all existing
           imports are preserved at the top
        """
        import re

        def _extract_imports(code: str) -> list[str]:
            """Extract import lines from code."""
            return [
                line.rstrip()
                for line in code.split('\n')
                if line.strip().startswith('import ')
            ]

        existing_imports = _extract_imports(existing)
        new_imports = _extract_imports(new_content)

        # Build a set of imported identifiers from existing imports to detect duplicates
        existing_import_set: set[str] = set()
        for imp in existing_imports:
            # Extract the from path: import { X } from './path.js'
            m = re.search(r"from\s+['\"]([^'\"]+)['\"]", imp)
            if m:
                existing_import_set.add(m.group(1))

        # Add new imports that aren't already present (by from-path)
        merged_imports = list(existing_imports)
        for imp in new_imports:
            m = re.search(r"from\s+['\"]([^'\"]+)['\"]", imp)
            if m and m.group(1) not in existing_import_set:
                merged_imports.append(imp)
                existing_import_set.add(m.group(1))
            elif not m and imp not in merged_imports:
                merged_imports.append(imp)

        # Remove import lines from new content to get the class body
        new_lines = new_content.split('\n')
        body_lines = [
            line for line in new_lines
            if not line.strip().startswith('import ')
        ]

        # Reconstruct: merged imports + body from new content
        result = '\n'.join(merged_imports) + '\n' + '\n'.join(body_lines)
        return result


    @staticmethod
    def _validate_js_brackets(content: str, file_path: str) -> str:
        """Validate and auto-repair unbalanced brackets in JS files.

        If the LLM output was truncated, braces/brackets may be unbalanced.
        This appends missing closers to prevent build failures.
        """
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        open_parens = content.count('(') - content.count(')')

        if open_braces <= 0 and open_brackets <= 0 and open_parens <= 0:
            return content

        # Auto-repair by appending missing closers
        repairs: list[str] = []
        if open_parens > 0:
            repairs.append(')' * open_parens)
        if open_brackets > 0:
            repairs.append(']' * open_brackets)
            repairs.append(';')
        if open_braces > 0:
            repairs.append('}' * open_braces)

        repaired = content.rstrip() + '\n' + '\n'.join(repairs) + '\n'
        logger.warning(
            "🔧 Auto-repaired %s: closed %d brace(s), %d bracket(s), %d paren(s)",
            file_path, max(0, open_braces), max(0, open_brackets), max(0, open_parens),
        )
        return repaired

    def _preflight_check_imports(self) -> None:
        """Scan all JS files for broken imports and auto-fix them.

        Checks every `import ... from './path'` statement to verify
        the imported file actually exists. Removes broken import lines
        and their usages (best-effort) to prevent build failures.
        """
        import re
        game_src = GAME_DIR / "src"
        if not game_src.exists():
            return

        import_pattern = re.compile(
            r"""^import\s+.*?\s+from\s+['"](\.\.?/.+?)['"];?\s*$""",
            re.MULTILINE,
        )

        fixed_count = 0
        # Skip scaffold files — their imports are resolved later
        SCAFFOLD_FILES = {"main.js"}
        for js_file in game_src.rglob("*.js"):
            if js_file.name in SCAFFOLD_FILES:
                continue
            content = js_file.read_text(encoding="utf-8", errors="replace")
            broken_imports: list[str] = []

            for m in import_pattern.finditer(content):
                import_path = m.group(1)
                # Resolve relative to the file's directory
                resolved = (js_file.parent / import_path).resolve()
                # Try with and without .js extension
                if not resolved.exists() and not resolved.with_suffix(".js").exists():
                    broken_imports.append(m.group(0))

            if broken_imports:
                for broken_line in broken_imports:
                    content = content.replace(broken_line, f"// REMOVED: broken import → {broken_line.strip()}")
                    logger.warning(
                        "🛡️ Pre-flight: removed broken import in %s → %s",
                        js_file.name, broken_line.strip()[:80],
                    )
                js_file.write_text(content, encoding="utf-8")
                fixed_count += len(broken_imports)

        if fixed_count:
            logger.info("🛡️ Pre-flight: fixed %d broken import(s) across game files", fixed_count)

    def get_current_files(self) -> dict[str, str]:
        """Read all current game source files for context."""
        game_src = GAME_DIR / "src"
        files: dict[str, str] = {}

        if not game_src.exists():
            return files

        for path in game_src.rglob("*.js"):
            relative = path.relative_to(GAME_DIR)
            try:
                files[str(relative)] = path.read_text(encoding="utf-8")
            except Exception:
                pass

        return files
