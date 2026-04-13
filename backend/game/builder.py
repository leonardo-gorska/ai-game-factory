"""
GORVAX GAME FACTORY — Game Builder
Compiles the game project using Vite via subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from backend.config import GAME_DIR, get_config

logger = logging.getLogger(__name__)


class GameBuilder:
    """
    Compiles the game project using Vite.
    Handles npm install, build, and dev server management.
    """

    _MAIN_JS_SCAFFOLD = """\
/**
 * GORVAX GAME FACTORY — Entry Point
 * Bootstraps the Phaser game. Part of the project scaffold.
 */
import Phaser from 'phaser';
import { BootScene } from './scenes/BootScene.js';
import { MainScene } from './scenes/MainScene.js';

const config = {
    type: Phaser.AUTO,
    parent: 'game-container',
    width: 800,
    height: 600,
    backgroundColor: '#0a0a1a',
    physics: {
        default: 'arcade',
        arcade: { gravity: { x: 0, y: 0 }, debug: false },
    },
    scene: [BootScene, MainScene],
    scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
    },
};

const game = new Phaser.Game(config);
export default game;
"""

    def __init__(self, game_dir: Path | None = None) -> None:
        self._game_dir = game_dir or GAME_DIR
        self._dev_process: asyncio.subprocess.Process | None = None
        self._game_port = get_config().server.game_port

    async def check_environment(self) -> dict[str, any]:
        """Validate the game build environment and auto-setup if needed.

        Checks Node.js, npm, package.json, creates src/ if missing,
        and runs npm install if node_modules is absent.

        Returns a dict with status info:
            ok (bool): True if environment is ready
            node_version (str): Node.js version or error
            npm_version (str): npm version or error
            npm_installed (bool): Whether npm install was run
            errors (list[str]): Any blocking errors
        """
        import sys

        result: dict[str, any] = {
            "ok": False,
            "node_version": "",
            "npm_version": "",
            "npm_installed": False,
            "errors": [],
        }

        # ── 1. Check Node.js ──────────────────────────────────
        try:
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    "node --version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "node", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            node_ver = stdout.decode().strip()
            if proc.returncode == 0 and node_ver:
                result["node_version"] = node_ver
                logger.info("✅ Node.js found: %s", node_ver)
            else:
                result["errors"].append("Node.js not found or returned error")
        except (FileNotFoundError, asyncio.TimeoutError):
            result["errors"].append(
                "Node.js not found. Install from https://nodejs.org/"
            )

        # ── 2. Check npm ──────────────────────────────────────
        try:
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    "npm --version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "npm", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            npm_ver = stdout.decode().strip()
            if proc.returncode == 0 and npm_ver:
                result["npm_version"] = npm_ver
                logger.info("✅ npm found: v%s", npm_ver)
            else:
                result["errors"].append("npm returned an error")
        except (FileNotFoundError, asyncio.TimeoutError):
            result["errors"].append(
                "npm not found. It usually comes with Node.js — "
                "try reinstalling from https://nodejs.org/"
            )

        # Stop early if critical tools missing
        if result["errors"]:
            return result

        # ── 3. Ensure package.json ────────────────────────────
        pkg_json = self._game_dir / "package.json"
        if not pkg_json.exists():
            result["errors"].append(
                f"package.json not found in {self._game_dir}. "
                "The game project scaffold is missing."
            )
            return result

        # ── 4. Ensure src/ directory ──────────────────────────
        src_dir = self._game_dir / "src"
        if not src_dir.exists():
            src_dir.mkdir(parents=True, exist_ok=True)
            logger.info("📁 Created game/src/ directory")

        # ── 4.5. Ensure main.js entry point ──────────────────
        main_js = src_dir / "main.js"
        if not main_js.exists():
            main_js.write_text(self._MAIN_JS_SCAFFOLD, encoding="utf-8")
            logger.info("📄 Created game/src/main.js scaffold")

        # ── 5. Install dependencies if needed ─────────────────
        node_modules = self._game_dir / "node_modules"
        if not node_modules.exists():
            logger.info("📦 node_modules missing — running npm install...")
            ok, output = await self._run_npm("install")
            result["npm_installed"] = True
            if not ok:
                result["errors"].append(f"npm install failed: {output[:500]}")
                return result
            logger.info("✅ npm install completed successfully")
        else:
            logger.info("✅ node_modules already present")

        result["ok"] = True
        return result

    async def ensure_dependencies(self) -> tuple[bool, str]:
        """Run npm install if node_modules doesn't exist."""
        node_modules = self._game_dir / "node_modules"
        if node_modules.exists():
            return True, "Dependencies already installed"

        logger.info("Installing game dependencies...")
        return await self._run_npm("install")

    async def build(self) -> tuple[bool, str]:
        """
        Build the game for production.
        Returns (success, output_text).
        """
        # Ensure dependencies first
        deps_ok, deps_output = await self.ensure_dependencies()
        if not deps_ok:
            return False, f"Dependency install failed:\n{deps_output}"

        # BE-15: Clean previous build artifacts
        dist_dir = self._game_dir / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir, ignore_errors=True)
            logger.info("Cleaned previous build artifacts: %s", dist_dir)

        logger.info("Building game...")
        success, output = await self._run_npm("run", "build")

        if success:
            logger.info("✅ Game build succeeded")
        else:
            logger.warning("❌ Game build failed:\n%s", output[-1000:])

        return success, output

    async def lint_check(self) -> tuple[bool, str]:
        """Run ESLint on game source files for real syntax/error checking."""
        game_src = self._game_dir / "src"
        if not game_src.exists():
            return False, "Game src directory does not exist"

        try:
            success, output = await self._run_npm("run", "lint")
            if success:
                return True, "ESLint: No errors found"
            # Extract meaningful error lines
            error_lines = []
            for line in output.split("\n"):
                line = line.strip()
                if "error" in line.lower() and line:
                    error_lines.append(line)
            return False, "\n".join(error_lines[:20]) if error_lines else output[:2000]
        except Exception:
            # Fallback: basic check if ESLint not available
            return await self._basic_lint_check()

    async def _basic_lint_check(self) -> tuple[bool, str]:
        """Fallback basic syntax check if ESLint is unavailable."""
        game_src = self._game_dir / "src"
        errors: list[str] = []
        for js_file in game_src.rglob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            if content.strip() == "":
                errors.append(f"{js_file.name}: File is empty")
            open_braces = content.count("{")
            close_braces = content.count("}")
            if abs(open_braces - close_braces) > 2:
                errors.append(
                    f"{js_file.name}: Mismatched braces "
                    f"(open={open_braces}, close={close_braces})"
                )
        if errors:
            return False, "\n".join(errors)
        return True, "Basic lint passed"

    async def start_dev_server(self) -> tuple[bool, str]:
        """Start the Vite dev server in the background."""
        if self._dev_process and self._dev_process.returncode is None:
            return True, "Dev server already running"

        deps_ok, deps_output = await self.ensure_dependencies()
        if not deps_ok:
            return False, deps_output

        try:
            import sys
            if sys.platform == "win32":
                cmd_str = f"npx vite --port {self._game_port} --host"
                self._dev_process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    cwd=str(self._game_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                self._dev_process = await asyncio.create_subprocess_exec(
                    "npx", "vite", "--port", str(self._game_port), "--host",
                    cwd=str(self._game_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            # Wait briefly for startup
            await asyncio.sleep(2)
            if self._dev_process.returncode is not None:
                stderr = await self._dev_process.stderr.read() if self._dev_process.stderr else b""
                return False, f"Dev server failed to start: {stderr.decode()}"

            logger.info("🎮 Game dev server started on http://localhost:%d", self._game_port)
            return True, f"Dev server running on http://localhost:{self._game_port}"

        except Exception as exc:
            return False, f"Failed to start dev server: {exc}"

    async def stop_dev_server(self) -> None:
        """Stop the Vite dev server."""
        if self._dev_process and self._dev_process.returncode is None:
            self._dev_process.terminate()
            try:
                await asyncio.wait_for(self._dev_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._dev_process.kill()
            logger.info("Game dev server stopped")

    async def _run_npm(self, *args: str) -> tuple[bool, str]:
        """Run an npm command and return (success, output).

        Uses shell mode on Windows because npm is a .cmd script that
        ``create_subprocess_exec`` cannot resolve directly.
        """
        import sys

        cmd_parts = ["npm", *args]

        try:
            if sys.platform == "win32":
                # Windows: npm is a .cmd — must run through shell
                cmd_str = " ".join(cmd_parts)
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    cwd=str(self._game_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    cwd=str(self._game_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )
            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            success = process.returncode == 0
            full_output = output
            if error_output:
                full_output += f"\n--- STDERR ---\n{error_output}"

            return success, full_output

        except asyncio.TimeoutError:
            return False, "npm command timed out (120s)"
        except FileNotFoundError:
            return False, "npm not found. Please install Node.js."
        except Exception as exc:
            return False, f"npm command failed: {exc}"

    def get_source_files(self) -> dict[str, str]:
        """Read all current game source files."""
        game_src = self._game_dir / "src"
        files: dict[str, str] = {}

        if not game_src.exists():
            return files

        for path in game_src.rglob("*.js"):
            relative = path.relative_to(self._game_dir)
            try:
                files[str(relative)] = path.read_text(encoding="utf-8")
            except Exception:
                pass

        return files
