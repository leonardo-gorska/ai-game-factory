/**
 * GORVAX TEMPLATE — Game Loop
 *
 * Features:
 * - Fixed timestep with variable rendering
 * - Delta time calculation
 * - FPS tracking and display
 * - Pause/resume support
 * - Performance monitoring
 */

class GameLoop {
    constructor(config = {}) {
        this.targetFPS = config.targetFPS || 60;
        this.fixedStep = 1000 / this.targetFPS;
        this.maxFrameSkip = config.maxFrameSkip || 5;
        this.isRunning = false;
        this.isPaused = false;

        // Callbacks
        this.updateFn = config.update || (() => { });
        this.renderFn = config.render || (() => { });

        // Timing
        this.lastTime = 0;
        this.accumulator = 0;
        this.frameCount = 0;
        this.fpsTimer = 0;
        this.currentFPS = 0;
        this.frameTime = 0;

        // Performance
        this.avgFrameTime = 0;
        this.frameTimes = [];
        this.maxFrameTimeSamples = 60;

        this._rafId = null;
        this._boundTick = this._tick.bind(this);
    }

    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        this.isPaused = false;
        this.lastTime = performance.now();
        this._rafId = requestAnimationFrame(this._boundTick);
    }

    stop() {
        this.isRunning = false;
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
    }

    pause() {
        this.isPaused = true;
    }

    resume() {
        if (this.isPaused) {
            this.isPaused = false;
            this.lastTime = performance.now();
            this.accumulator = 0;
        }
    }

    _tick(timestamp) {
        if (!this.isRunning) return;

        const frameStart = performance.now();
        const elapsed = timestamp - this.lastTime;
        this.lastTime = timestamp;

        // FPS counter
        this.fpsTimer += elapsed;
        this.frameCount++;
        if (this.fpsTimer >= 1000) {
            this.currentFPS = this.frameCount;
            this.frameCount = 0;
            this.fpsTimer -= 1000;
        }

        if (!this.isPaused) {
            // Fixed timestep updates
            this.accumulator += Math.min(elapsed, this.fixedStep * this.maxFrameSkip);
            let updates = 0;
            while (this.accumulator >= this.fixedStep && updates < this.maxFrameSkip) {
                this.updateFn(this.fixedStep / 1000); // dt in seconds
                this.accumulator -= this.fixedStep;
                updates++;
            }

            // Render with interpolation factor
            const alpha = this.accumulator / this.fixedStep;
            this.renderFn(alpha);
        }

        // Performance tracking
        this.frameTime = performance.now() - frameStart;
        this.frameTimes.push(this.frameTime);
        if (this.frameTimes.length > this.maxFrameTimeSamples) {
            this.frameTimes.shift();
        }
        this.avgFrameTime = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;

        this._rafId = requestAnimationFrame(this._boundTick);
    }

    getPerformanceStats() {
        return {
            fps: this.currentFPS,
            frameTime: this.frameTime.toFixed(2),
            avgFrameTime: this.avgFrameTime.toFixed(2),
            isRunning: this.isRunning,
            isPaused: this.isPaused,
        };
    }
}
