/**
 * GORVAX TEMPLATE — HUD (Heads-Up Display)
 *
 * Features:
 * - HP/MP/Stamina bars with animated transitions
 * - Gold/currency display
 * - Minimap indicator
 * - Status effect icons
 * - Responsive canvas rendering
 */

class HUD {
    constructor(canvas, config = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.width = canvas.width;
        this.height = canvas.height;
        this.padding = config.padding || 10;
        this.barHeight = config.barHeight || 20;
        this.barWidth = config.barWidth || 200;
        this.fontSize = config.fontSize || 14;
        this.animationSpeed = config.animationSpeed || 5;

        // Animated bar values (smoothly lerp to target)
        this._displayValues = { hp: 1, mp: 1, stamina: 1 };
        this._targetValues = { hp: 1, mp: 1, stamina: 1 };

        this.statusEffects = [];
        this.notifications = [];
    }

    update(dt, playerData) {
        // Update targets
        this._targetValues.hp = playerData.hp / playerData.maxHp;
        this._targetValues.mp = playerData.mp / playerData.maxMp;
        this._targetValues.stamina = (playerData.stamina || 0) / (playerData.maxStamina || 1);

        // Smooth animation
        for (const key of Object.keys(this._displayValues)) {
            const diff = this._targetValues[key] - this._displayValues[key];
            this._displayValues[key] += diff * this.animationSpeed * dt;
        }

        // Notification decay
        this.notifications = this.notifications.filter(n => {
            n.ttl -= dt * 1000;
            n.y -= 20 * dt;
            n.alpha = Math.max(0, n.ttl / n.maxTtl);
            return n.ttl > 0;
        });

        this.playerData = playerData;
    }

    render() {
        const ctx = this.ctx;
        const p = this.padding;

        // ── HP Bar ──
        this._drawBar(p, p, this._displayValues.hp, '#e74c3c', '#c0392b',
            `HP: ${this.playerData.hp}/${this.playerData.maxHp}`);

        // ── MP Bar ──
        this._drawBar(p, p + this.barHeight + 5, this._displayValues.mp, '#3498db', '#2980b9',
            `MP: ${this.playerData.mp}/${this.playerData.maxMp}`);

        // ── Stamina Bar ──
        if (this.playerData.maxStamina) {
            this._drawBar(p, p + (this.barHeight + 5) * 2, this._displayValues.stamina, '#2ecc71', '#27ae60',
                `STA: ${Math.floor(this.playerData.stamina)}/${this.playerData.maxStamina}`);
        }

        // ── Gold ──
        ctx.fillStyle = '#f1c40f';
        ctx.font = `bold ${this.fontSize}px monospace`;
        ctx.textAlign = 'right';
        ctx.fillText(`💰 ${this.playerData.gold || 0}`, this.width - p, p + this.fontSize);

        // ── Level ──
        ctx.fillStyle = '#ecf0f1';
        ctx.textAlign = 'right';
        ctx.fillText(`Lv. ${this.playerData.level || 1}`, this.width - p, p + this.fontSize * 2.5);

        // ── Status Effects ──
        this._renderStatusEffects(p, p + (this.barHeight + 5) * 3 + 10);

        // ── Notifications ──
        this._renderNotifications();
    }

    _drawBar(x, y, ratio, fgColor, bgColor, label) {
        const ctx = this.ctx;
        const w = this.barWidth;
        const h = this.barHeight;

        // Background
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(x, y, w, h);

        // Fill
        ctx.fillStyle = ratio > 0.25 ? fgColor : '#e74c3c';
        ctx.fillRect(x, y, w * Math.max(0, ratio), h);

        // Border
        ctx.strokeStyle = bgColor;
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, w, h);

        // Label
        ctx.fillStyle = '#fff';
        ctx.font = `${this.fontSize - 2}px monospace`;
        ctx.textAlign = 'center';
        ctx.fillText(label, x + w / 2, y + h / 2 + 4);
    }

    _renderStatusEffects(x, y) {
        const ctx = this.ctx;
        const size = 24;
        this.statusEffects.forEach((effect, i) => {
            ctx.fillStyle = effect.color || '#9b59b6';
            ctx.fillRect(x + i * (size + 4), y, size, size);
            ctx.fillStyle = '#fff';
            ctx.font = '10px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(effect.icon || '?', x + i * (size + 4) + size / 2, y + size / 2 + 3);
        });
    }

    _renderNotifications() {
        const ctx = this.ctx;
        this.notifications.forEach(n => {
            ctx.globalAlpha = n.alpha;
            ctx.fillStyle = n.color || '#f1c40f';
            ctx.font = `bold ${this.fontSize}px monospace`;
            ctx.textAlign = 'center';
            ctx.fillText(n.text, this.width / 2, n.y);
            ctx.globalAlpha = 1;
        });
    }

    addNotification(text, color = '#f1c40f', ttl = 2000) {
        this.notifications.push({
            text, color, ttl, maxTtl: ttl,
            y: this.height * 0.3, alpha: 1,
        });
    }

    setStatusEffects(effects) {
        this.statusEffects = effects;
    }
}
