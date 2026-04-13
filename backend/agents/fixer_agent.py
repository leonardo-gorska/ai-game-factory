"""
GORVAX GAME FACTORY — Fixer Agent
Specialized LLM agent for debugging build and runtime errors.

Unlike the Developer agent, the Fixer:
- Has NO access to GDD or feature context
- CAN modify BLOCKED_FILES (main.js, BootScene.js)
- Focuses ONLY on fixing the specific error described
- Uses a debugging-specialized prompt
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.utils.json_parser import extract_json_from_response
from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR, GAME_DIR

logger = logging.getLogger(__name__)

# Maximum number of parse retries before giving up
_MAX_PARSE_RETRIES = 1


class FixerAgent(BaseAgent):
    """
    Specialized debugging agent. Fixes build errors and runtime errors
    without adding features or modifying game design.

    Key differences from DeveloperAgent:
    - No GDD context → focused purely on the bug
    - Empty BLOCKED_FILES → can modify main.js, BootScene.js
    - Debugging-specialized prompt
    - Minimal code changes only
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "fixer.md").read_text(encoding="utf-8")
        super().__init__(
            name="fixer",
            role="Bug Fixer",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Fix build or runtime errors in game code.

        input_data should contain:
          - build_errors: list[str] (classified error messages)
          - current_files: dict[str, str] (current game source files)
          - console_errors: list[str] (optional, runtime errors from headless tester)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.2,  # Very low temperature for precise fixes
                max_tokens=8192,
                json_mode=True,
            )

            code_changes = self._parse_code_response(response)
            files_list = code_changes.get("files", [])

            # Retry if no files were produced
            if not files_list:
                logger.warning(
                    "Fixer produced 0 files on iteration %d. Retrying...",
                    iteration,
                )
                retry_response = await self._call_llm(
                    prompt=self._build_retry_prompt(response),
                    context="",
                    temperature=0.1,
                    max_tokens=8192,
                    json_mode=True,
                )
                code_changes = self._parse_code_response(retry_response)
                files_list = code_changes.get("files", [])

            files_written = await self._write_files(code_changes)

            if files_written:
                logger.info(
                    "🔧 Fixer wrote %d file(s) on iteration %d: %s",
                    len(files_written), iteration,
                    ", ".join(files_written[:5]),
                )
            else:
                logger.warning(
                    "⚠️ Fixer wrote 0 files on iteration %d",
                    iteration,
                )

            return AgentResult(
                agent_name=self.name,
                action="fix_code",
                output=json.dumps({
                    "summary": code_changes.get("summary", "Bug fix applied"),
                    "fix_description": code_changes.get("fix_description", ""),
                    "files_modified": files_written,
                }),
                success=True,
                metadata={
                    "code_changes": code_changes,
                    "files_written": files_written,
                },
            )

        except Exception as exc:
            logger.error("Fixer failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="fix_code",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build a debugging-focused prompt (no GDD, no features)."""
        parts: list[str] = []

        # Build errors — primary input
        build_errors = input_data.get("build_errors", [])
        if build_errors:
            errors_text = "\n".join(f"- {e}" for e in build_errors)
            parts.append(
                f"## 🔴 BUILD ERRORS — Fix these ONLY\n{errors_text}\n"
            )

        # Console/runtime errors from headless tester
        console_errors = input_data.get("console_errors", [])
        if console_errors:
            errors_text = "\n".join(f"- {e}" for e in console_errors[:20])
            parts.append(
                f"## 🔴 RUNTIME ERRORS (from browser console)\n{errors_text}\n"
            )

        # Current files for context
        current_files = input_data.get("current_files", {})
        if current_files:
            files_context = []
            for path, content in current_files.items():
                # Full context for small files, truncated for large ones
                limit = 6000
                truncated = content[:limit] + "..." if len(content) > limit else content
                files_context.append(f"### {path}\n```javascript\n{truncated}\n```")
            parts.append(f"## Current Game Files\n{''.join(files_context)}\n")

        # Failed attempt memory
        failed_fixes = input_data.get("failed_fixes", [])
        if failed_fixes:
            memory_text = "\n".join(f"{i}. {fix}" for i, fix in enumerate(failed_fixes[-3:], 1))
            parts.append(
                f"## ❌ Previous fix attempts that FAILED — do NOT repeat:\n{memory_text}\n"
            )

        parts.append(
            "Fix the errors above. Change the MINIMUM amount of code necessary.\n"
            "Respond with ONLY the JSON format specified in your instructions.\n\n"
            "REMINDER: Your response MUST be a single valid JSON object with this structure:\n"
            '{"summary": "...", "files": [{"path": "src/...", "action": "modify", "content": "..."}], '
            '"fix_description": "..."}'
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
            '  "summary": "Brief description of the fix",\n'
            '  "files": [\n'
            '    {"path": "src/file.js", "action": "modify", "content": "// full file content"}\n'
            "  ],\n"
            '  "fix_description": "Root cause and fix"\n'
            "}\n"
            "```\n\n"
            "Here is your previous response. Convert it to the JSON format above:\n\n"
            f"{failed_response[:8000]}"
        )

    def _parse_code_response(self, response: str) -> dict[str, Any]:
        """Extract code changes JSON from the LLM response."""
        return extract_json_from_response(response, fallback={
            "summary": "Bug fix (raw response)",
            "files": [],
            "raw_response": response[:1000],
        })

    async def _write_files(self, code_changes: dict[str, Any]) -> list[str]:
        """Write fixed code files to the game directory.

        Unlike the Developer agent, the Fixer has NO blocked files —
        it can modify main.js, BootScene.js, and any other file.
        """
        files_written: list[str] = []
        game_src = GAME_DIR / "src"

        # Fixer has NO blocked files — can edit anything under game/src/
        BLOCKED_FILES: set[str] = {
            "vite.config.js", "package.json", "index.html",
            ".eslintrc.js", ".eslintrc.json", "game.js", "game_config.json",
        }

        for file_entry in code_changes.get("files", []):
            file_path = file_entry.get("path", "")
            action = file_entry.get("action", "modify")
            content = file_entry.get("content", "")

            if not file_path or not content:
                continue

            basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

            # Block only build-config files — NOT game source files
            if basename in BLOCKED_FILES:
                logger.warning("🛡️ Fixer: blocked write to config file: %s", file_path)
                continue

            # Normalize path
            if file_path.startswith("src/"):
                full_path = GAME_DIR / file_path
            elif file_path.startswith("game/src/"):
                full_path = GAME_DIR / file_path.replace("game/", "", 1)
            else:
                full_path = game_src / file_path

            # SEC-03: Block path traversal
            resolved = full_path.resolve()
            game_resolved = GAME_DIR.resolve()
            if not str(resolved).startswith(str(game_resolved)):
                logger.warning("🛡️ Fixer: path traversal blocked: %s → %s", file_path, resolved)
                continue

            if action == "delete":
                if full_path.exists():
                    full_path.unlink()
                    files_written.append(f"DELETED: {file_path}")
                continue

            # Create directory if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Validate JS bracket balance before writing
            content = self._validate_js_brackets(content, file_path)

            # Write the file
            full_path.write_text(content, encoding="utf-8")
            files_written.append(str(file_path))
            logger.info("🔧 Fixer wrote: %s (%d bytes)", full_path, len(content))

        return files_written

    @staticmethod
    def _validate_js_brackets(content: str, file_path: str) -> str:
        """Validate and auto-repair unbalanced brackets in JS files."""
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        open_parens = content.count('(') - content.count(')')

        if open_braces <= 0 and open_brackets <= 0 and open_parens <= 0:
            return content

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
            "🔧 Fixer auto-repaired %s: closed %d brace(s), %d bracket(s), %d paren(s)",
            file_path, max(0, open_braces), max(0, open_brackets), max(0, open_parens),
        )
        return repaired
