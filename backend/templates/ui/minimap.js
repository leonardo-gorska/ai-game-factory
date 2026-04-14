/**
 * GORVAX TEMPLATE — Minimap System
 *
 * Features:
 * - Canvas-based minimap rendering
 * - Player position tracking
 * - Entity markers (enemies, NPCs, objectives)
 * - Fog of war
 * - Zoom levels
 */

class Minimap {
    constructor(canvas, worldWidth, worldHeight, config = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.mapWidth = config.mapWidth || 150;
        this.mapHeight = config.mapHeight || 150;
        this.worldWidth = worldWidth;
        this.worldHeight = worldHeight;
        this.x = config.x || (canvas.width - this.mapWidth - 10);
        this.y = config.y || 10;
        this.zoom = config.zoom || 1;
        this.fogOfWar = config.fogOfWar !== false;
        this.revealedCells = new Set();
        this.cellSize = config.cellSize || 32;
        this.markers = [];
        this.terrainColors = config.terrainColors || {
            ground: '#2d5a1e',
            water: '#1a6fa0',
            wall: '#4a4a4a',
            path: '#8b7355',
        };
    }

    get scaleX() {
        return this.mapWidth / (this.worldWidth * this.zoom);
    }

    get scaleY() {
        return this.mapHeight / (this.worldHeight * this.zoom);
    }

    update(playerX, playerY, entities = []) {
        this.playerX = playerX;
        this.playerY = playerY;

        // Reveal fog around player
        if (this.fogOfWar) {
            const revealRadius = 5;
            const cellX = Math.floor(playerX / this.cellSize);
            const cellY = Math.floor(playerY / this.cellSize);
            for (let dx = -revealRadius; dx <= revealRadius; dx++) {
                for (let dy = -revealRadius; dy <= revealRadius; dy++) {
                    if (dx * dx + dy * dy <= revealRadius * revealRadius) {
                        this.revealedCells.add(`${cellX + dx},${cellY + dy}`);
                    }
                }
            }
        }

        // Update markers
        this.markers = entities.map(e => ({
            x: e.x,
            y: e.y,
            type: e.type || 'enemy',
            color: e.minimapColor || this._markerColor(e.type),
        }));
    }

    render(terrainGrid = null) {
        const ctx = this.ctx;

        // Background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(this.x, this.y, this.mapWidth, this.mapHeight);

        // Border
        ctx.strokeStyle = '#888';
        ctx.lineWidth = 2;
        ctx.strokeRect(this.x, this.y, this.mapWidth, this.mapHeight);

        // Clip to minimap area
        ctx.save();
        ctx.beginPath();
        ctx.rect(this.x, this.y, this.mapWidth, this.mapHeight);
        ctx.clip();

        // Terrain
        if (terrainGrid) {
            this._renderTerrain(terrainGrid);
        }

        // Entity markers
        this.markers.forEach(m => {
            if (this.fogOfWar && !this._isRevealed(m.x, m.y)) return;
            const mx = this.x + m.x * this.scaleX;
            const my = this.y + m.y * this.scaleY;
            ctx.fillStyle = m.color;
            ctx.beginPath();
            ctx.arc(mx, my, 3, 0, Math.PI * 2);
            ctx.fill();
        });

        // Player marker
        const px = this.x + this.playerX * this.scaleX;
        const py = this.y + this.playerY * this.scaleY;
        ctx.fillStyle = '#f1c40f';
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.restore();
    }

    _renderTerrain(grid) {
        const ctx = this.ctx;
        const cellW = this.mapWidth / grid[0].length;
        const cellH = this.mapHeight / grid.length;

        for (let row = 0; row < grid.length; row++) {
            for (let col = 0; col < grid[row].length; col++) {
                if (this.fogOfWar && !this.revealedCells.has(`${col},${row}`)) {
                    ctx.fillStyle = '#111';
                } else {
                    ctx.fillStyle = this.terrainColors[grid[row][col]] || '#333';
                }
                ctx.fillRect(this.x + col * cellW, this.y + row * cellH, cellW + 1, cellH + 1);
            }
        }
    }

    _isRevealed(worldX, worldY) {
        const cellX = Math.floor(worldX / this.cellSize);
        const cellY = Math.floor(worldY / this.cellSize);
        return this.revealedCells.has(`${cellX},${cellY}`);
    }

    _markerColor(type) {
        const colors = {
            enemy: '#e74c3c',
            npc: '#2ecc71',
            objective: '#f39c12',
            item: '#3498db',
            boss: '#9b59b6',
        };
        return colors[type] || '#aaa';
    }

    setZoom(level) {
        this.zoom = Math.max(0.5, Math.min(4, level));
    }
}
