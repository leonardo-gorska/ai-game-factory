"""
GORVAX GAME FACTORY — Headless Browser Tester (P11)
Runs the actual Phaser game in a headless Chromium via Playwright,
capturing console errors, crashes, FPS and screenshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import get_config

logger = logging.getLogger(__name__)

# Default observation time (seconds)
DEFAULT_OBSERVE_SECONDS = 10
# Page load timeout
PAGE_LOAD_TIMEOUT_MS = 15_000


@dataclass
class HeadlessTestResult:
    """Headless test result."""
    page_loaded: bool = False
    load_time_ms: float = 0
    console_errors: list[str] = field(default_factory=list)
    console_warnings: list[str] = field(default_factory=list)
    js_exceptions: list[str] = field(default_factory=list)
    fps_samples: list[float] = field(default_factory=list)
    avg_fps: float = 0
    min_fps: float = 0
    screenshot_path: str = ""
    canvas_detected: bool = False
    phaser_detected: bool = False
    game_started: bool = False
    observe_duration_s: float = 0
    crash_detected: bool = False
    network_errors: list[str] = field(default_factory=list)

    @property
    def health_score(self) -> float:
        """Health score 0–100 based on results."""
        score = 0.0

        # Page loaded? (20 pts)
        if self.page_loaded:
            score += 20

        # Canvas/Phaser detected? (20 pts)
        if self.canvas_detected:
            score += 10
        if self.phaser_detected:
            score += 10

        # Game started? (20 pts)
        if self.game_started:
            score += 20

        # Console errors (20 pts max, -5 per error)
        error_penalty = min(20, len(self.console_errors) * 5)
        score += 20 - error_penalty

        # FPS (20 pts)
        if self.avg_fps > 0:
            if self.avg_fps >= 50:
                score += 20
            elif self.avg_fps >= 30:
                score += 15
            elif self.avg_fps >= 15:
                score += 10
            else:
                score += 5

        # JS exceptions are severe
        if self.js_exceptions:
            score -= min(30, len(self.js_exceptions) * 10)

        # Crash is fatal
        if self.crash_detected:
            score = min(score, 10)

        return max(0.0, min(100.0, score))

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_loaded": self.page_loaded,
            "load_time_ms": round(self.load_time_ms, 1),
            "console_errors": self.console_errors[:10],
            "console_warnings": self.console_warnings[:5],
            "js_exceptions": self.js_exceptions[:5],
            "avg_fps": round(self.avg_fps, 1),
            "min_fps": round(self.min_fps, 1),
            "canvas_detected": self.canvas_detected,
            "phaser_detected": self.phaser_detected,
            "game_started": self.game_started,
            "crash_detected": self.crash_detected,
            "health_score": round(self.health_score, 1),
            "network_errors": self.network_errors[:5],
            "observe_duration_s": round(self.observe_duration_s, 1),
        }


class HeadlessTester:
    """
    Tests the Phaser game in a headless Chromium via Playwright.

    Flow:
    1. Opens the game in the browser (via dev server URL)
    2. Collects console errors and JS exceptions
    3. Detects canvas/Phaser/game start
    4. Measures FPS via requestAnimationFrame
    5. Takes a screenshot
    """

    def __init__(
        self,
        game_url: str = "http://localhost:5173",
        screenshot_dir: Path | None = None,
    ) -> None:
        # B4: Read game port from configuration instead of hardcoded value
        self._game_url = f"http://localhost:{get_config().server.game_port}"
        self._screenshot_dir = screenshot_dir or Path("data/screenshots")
        self._available: bool | None = None

    async def is_available(self) -> bool:
        """Check if Playwright is installed and available."""
        if self._available is not None:
            return self._available
        import importlib.util
        if importlib.util.find_spec("playwright") is not None:
            self._available = True
        else:
            logger.warning(
                "⚠️ Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            self._available = False
        return self._available

    async def run_test(
        self,
        iteration: int,
        observe_seconds: float = DEFAULT_OBSERVE_SECONDS,
    ) -> HeadlessTestResult:
        """Run a complete headless test."""
        result = HeadlessTestResult()

        if not await self.is_available():
            logger.info("Headless tester not available, returning empty result")
            return result

        from playwright.async_api import async_playwright

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()

                # Collect console messages
                page.on("console", lambda msg: self._on_console(msg, result))
                page.on("pageerror", lambda err: self._on_page_error(err, result))

                # Collect network errors
                page.on("requestfailed", lambda req: result.network_errors.append(
                    f"{req.method} {req.url}: {req.failure}"
                ))

                # Navigate to the game
                t_start = time.monotonic()
                try:
                    response = await page.goto(
                        self._game_url,
                        timeout=PAGE_LOAD_TIMEOUT_MS,
                        wait_until="networkidle",
                    )
                    result.load_time_ms = (time.monotonic() - t_start) * 1000
                    result.page_loaded = response is not None and response.ok
                except Exception as exc:
                    logger.warning("Page load failed: %s", exc)
                    result.page_loaded = False
                    result.load_time_ms = (time.monotonic() - t_start) * 1000
                    await browser.close()
                    return result

                # Wait briefly for Phaser to initialize
                await asyncio.sleep(2)

                # Detect canvas and Phaser
                result.canvas_detected = await page.evaluate(
                    "() => document.querySelector('canvas') !== null"
                )
                result.phaser_detected = await page.evaluate(
                    "() => typeof window.Phaser !== 'undefined'"
                )
                result.game_started = await page.evaluate("""() => {
                    if (typeof window.Phaser === 'undefined') return false;
                    // Check if there's an active game instance
                    const games = Phaser.GAMES || [];
                    if (games.length === 0) return false;
                    const g = games[0];
                    // Phaser 3.60+ removed isRunning — use isBooted + active scenes
                    if (g.isRunning === true) return true;
                    if (g.isBooted && g.scene && g.scene.scenes && g.scene.scenes.length > 0) return true;
                    // Fallback: check if canvas has non-zero dimensions (game is rendering)
                    if (g.canvas && g.canvas.width > 0 && g.canvas.height > 0) return true;
                    return false;
                }""")

                # Inject FPS meter via requestAnimationFrame
                await page.evaluate("""() => {
                    window.__fps_samples = [];
                    let lastTime = performance.now();
                    let frameCount = 0;
                    function measureFPS() {
                        frameCount++;
                        const now = performance.now();
                        if (now - lastTime >= 1000) {
                            window.__fps_samples.push(frameCount);
                            frameCount = 0;
                            lastTime = now;
                        }
                        requestAnimationFrame(measureFPS);
                    }
                    requestAnimationFrame(measureFPS);
                }""")

                # Observe the game running
                t_observe_start = time.monotonic()
                await asyncio.sleep(observe_seconds)
                result.observe_duration_s = time.monotonic() - t_observe_start

                # Collect FPS samples
                fps_data = await page.evaluate("() => window.__fps_samples || []")
                if fps_data:
                    result.fps_samples = [float(f) for f in fps_data]
                    result.avg_fps = sum(result.fps_samples) / len(result.fps_samples)
                    result.min_fps = min(result.fps_samples)

                # Detect crash (if many errors or FPS dropped to zero)
                if len(result.js_exceptions) >= 3 or (result.avg_fps > 0 and result.avg_fps < 5):
                    result.crash_detected = True

                # Screenshot
                try:
                    self._screenshot_dir.mkdir(parents=True, exist_ok=True)
                    ss_path = self._screenshot_dir / f"iter_{iteration}.png"
                    await page.screenshot(path=str(ss_path), full_page=False)
                    result.screenshot_path = str(ss_path)
                    logger.info("📸 Screenshot saved: %s", ss_path)
                except Exception as exc:
                    logger.debug("Screenshot failed: %s", exc)

                await browser.close()

        except Exception as exc:
            logger.error("Headless test failed: %s", exc)
            result.crash_detected = True

        logger.info(
            "🎮 Headless test: loaded=%s, canvas=%s, phaser=%s, fps=%.0f, errors=%d, health=%.0f",
            result.page_loaded, result.canvas_detected, result.phaser_detected,
            result.avg_fps, len(result.console_errors), result.health_score,
        )
        return result

    def _on_console(self, msg: Any, result: HeadlessTestResult) -> None:
        """Handle console messages."""
        text = str(msg.text)[:500]
        if msg.type == "error":
            result.console_errors.append(text)
        elif msg.type == "warning":
            result.console_warnings.append(text)

    def _on_page_error(self, error: Any, result: HeadlessTestResult) -> None:
        """Handle uncaught JS exceptions."""
        result.js_exceptions.append(str(error)[:500])
