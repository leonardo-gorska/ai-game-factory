/**
 * GORVAX TEMPLATE — Real-Time Combat System
 *
 * Features:
 * - Cooldown-based abilities
 * - Hitbox collision detection (AABB)
 * - Damage numbers with knockback
 * - Combo system
 * - Invincibility frames (i-frames)
 */

class Hitbox {
    constructor(x, y, width, height) {
        this.x = x;
        this.y = y;
        this.width = width;
        this.height = height;
    }

    intersects(other) {
        return (
            this.x < other.x + other.width &&
            this.x + this.width > other.x &&
            this.y < other.y + other.height &&
            this.y + this.height > other.y
        );
    }
}

class CombatAbility {
    constructor(id, name, damage, cooldown, range = 50, knockback = 0) {
        this.id = id;
        this.name = name;
        this.damage = damage;
        this.cooldown = cooldown; // seconds
        this.range = range;
        this.knockback = knockback;
        this.lastUsed = -Infinity;
    }

    isReady(currentTime) {
        return currentTime - this.lastUsed >= this.cooldown * 1000;
    }

    use(currentTime) {
        this.lastUsed = currentTime;
    }

    getRemainingCooldown(currentTime) {
        const elapsed = (currentTime - this.lastUsed) / 1000;
        return Math.max(0, this.cooldown - elapsed);
    }
}

class RealtimeCombatEntity {
    constructor(name, x, y, stats) {
        this.name = name;
        this.x = x;
        this.y = y;
        this.hp = stats.maxHp || 100;
        this.maxHp = stats.maxHp || 100;
        this.attack = stats.attack || 10;
        this.speed = stats.speed || 200; // pixels per second
        this.abilities = (stats.abilities || []).map(
            a => new CombatAbility(a.id, a.name, a.damage, a.cooldown, a.range, a.knockback)
        );
        this.hitbox = new Hitbox(x, y, stats.width || 32, stats.height || 32);
        this.vx = 0;
        this.vy = 0;
        this.isAlive = true;
        this.iFrames = 0; // invincibility frames in ms
        this.comboCount = 0;
        this.comboTimer = 0;
        this.damageNumbers = [];
    }

    update(dt) {
        // Movement
        this.x += this.vx * dt;
        this.y += this.vy * dt;
        this.hitbox.x = this.x;
        this.hitbox.y = this.y;

        // I-frames
        if (this.iFrames > 0) this.iFrames -= dt * 1000;

        // Combo decay
        if (this.comboTimer > 0) {
            this.comboTimer -= dt * 1000;
            if (this.comboTimer <= 0) this.comboCount = 0;
        }

        // Damage number cleanup
        this.damageNumbers = this.damageNumbers.filter(d => d.ttl > 0);
        this.damageNumbers.forEach(d => {
            d.y -= 30 * dt;
            d.ttl -= dt * 1000;
        });
    }

    takeDamage(amount, knockbackX = 0, knockbackY = 0) {
        if (this.iFrames > 0 || !this.isAlive) return 0;

        this.hp = Math.max(0, this.hp - amount);
        this.iFrames = 200; // 200ms of invincibility

        // Knockback
        this.vx += knockbackX;
        this.vy += knockbackY;

        // Damage number
        this.damageNumbers.push({
            value: amount,
            x: this.x + this.hitbox.width / 2,
            y: this.y,
            ttl: 800,
        });

        if (this.hp <= 0) this.isAlive = false;
        return amount;
    }

    useAbility(abilityId, target, currentTime) {
        const ability = this.abilities.find(a => a.id === abilityId);
        if (!ability || !ability.isReady(currentTime)) return null;

        // Range check
        const dx = target.x - this.x;
        const dy = target.y - this.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > ability.range) return null;

        ability.use(currentTime);

        // Combo
        this.comboCount++;
        this.comboTimer = 1500;
        const comboMultiplier = 1 + this.comboCount * 0.1;
        const totalDamage = Math.floor((this.attack + ability.damage) * comboMultiplier);

        // Knockback direction
        const angle = Math.atan2(dy, dx);
        const kbX = Math.cos(angle) * ability.knockback;
        const kbY = Math.sin(angle) * ability.knockback;

        target.takeDamage(totalDamage, kbX, kbY);

        return { damage: totalDamage, combo: this.comboCount, ability: ability.name };
    }
}

class RealtimeCombatSystem {
    constructor() {
        this.entities = [];
        this.projectiles = [];
    }

    addEntity(entity) {
        this.entities.push(entity);
    }

    update(dt) {
        this.entities.forEach(e => e.update(dt));
        this.entities = this.entities.filter(e => e.isAlive);
    }

    checkCollisions() {
        const collisions = [];
        for (let i = 0; i < this.entities.length; i++) {
            for (let j = i + 1; j < this.entities.length; j++) {
                if (this.entities[i].hitbox.intersects(this.entities[j].hitbox)) {
                    collisions.push([this.entities[i], this.entities[j]]);
                }
            }
        }
        return collisions;
    }
}
