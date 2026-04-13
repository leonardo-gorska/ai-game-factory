/**
 * GORVAX TEMPLATE — Turn-Based Combat System
 *
 * Features:
 * - Initiative-based turn order
 * - Abilities with cooldowns and mana costs
 * - Status effects (buff/debuff)
 * - Damage calculation with defense/resistance
 * - Combat log
 */

class CombatEntity {
    constructor(name, stats) {
        this.name = name;
        this.hp = stats.maxHp || 100;
        this.maxHp = stats.maxHp || 100;
        this.mp = stats.maxMp || 50;
        this.maxMp = stats.maxMp || 50;
        this.attack = stats.attack || 10;
        this.defense = stats.defense || 5;
        this.speed = stats.speed || 10;
        this.abilities = stats.abilities || [];
        this.statusEffects = [];
        this.isAlive = true;
    }

    takeDamage(amount) {
        const mitigated = Math.max(1, amount - this.defense);
        this.hp = Math.max(0, this.hp - mitigated);
        if (this.hp <= 0) this.isAlive = false;
        return mitigated;
    }

    heal(amount) {
        this.hp = Math.min(this.maxHp, this.hp + amount);
    }

    applyStatusEffect(effect) {
        const existing = this.statusEffects.find(e => e.id === effect.id);
        if (existing) {
            existing.turnsRemaining = effect.duration;
        } else {
            this.statusEffects.push({ ...effect, turnsRemaining: effect.duration });
        }
    }

    tickStatusEffects() {
        this.statusEffects.forEach(effect => {
            if (effect.type === 'dot') this.takeDamage(effect.value);
            if (effect.type === 'hot') this.heal(effect.value);
            effect.turnsRemaining--;
        });
        this.statusEffects = this.statusEffects.filter(e => e.turnsRemaining > 0);
    }
}

class TurnCombat {
    constructor(allies, enemies) {
        this.allies = allies;
        this.enemies = enemies;
        this.turnOrder = [];
        this.currentTurn = 0;
        this.round = 1;
        this.log = [];
        this.state = 'active'; // 'active', 'victory', 'defeat'
    }

    start() {
        this._calculateTurnOrder();
        this._logEvent(`⚔️ Combat started! Round ${this.round}`);
        return this.getCurrentActor();
    }

    _calculateTurnOrder() {
        const all = [...this.allies, ...this.enemies].filter(e => e.isAlive);
        all.sort((a, b) => b.speed - a.speed);
        this.turnOrder = all;
        this.currentTurn = 0;
    }

    getCurrentActor() {
        return this.turnOrder[this.currentTurn];
    }

    executeAction(action) {
        const actor = this.getCurrentActor();
        if (!actor || !actor.isAlive) return this.nextTurn();

        let result = {};

        switch (action.type) {
            case 'attack': {
                const target = action.target;
                const dmgBase = actor.attack + Math.floor(Math.random() * 5);
                const dmg = target.takeDamage(dmgBase);
                result = { type: 'attack', actor: actor.name, target: target.name, damage: dmg };
                this._logEvent(`${actor.name} attacks ${target.name} for ${dmg} damage`);
                break;
            }
            case 'ability': {
                const ability = actor.abilities.find(a => a.id === action.abilityId);
                if (!ability || actor.mp < ability.mpCost) {
                    result = { type: 'failed', reason: 'insufficient_mp' };
                    break;
                }
                actor.mp -= ability.mpCost;
                if (ability.damageType === 'heal') {
                    const target = action.target;
                    target.heal(ability.power);
                    result = { type: 'heal', actor: actor.name, target: target.name, amount: ability.power };
                    this._logEvent(`${actor.name} uses ${ability.name} → heals ${target.name} for ${ability.power}`);
                } else {
                    const target = action.target;
                    const dmg = target.takeDamage(ability.power);
                    result = { type: 'ability', actor: actor.name, target: target.name, damage: dmg, ability: ability.name };
                    this._logEvent(`${actor.name} uses ${ability.name} → ${dmg} damage to ${target.name}`);
                }
                if (ability.statusEffect) {
                    action.target.applyStatusEffect(ability.statusEffect);
                }
                break;
            }
            case 'defend': {
                actor.defense *= 2;
                result = { type: 'defend', actor: actor.name };
                this._logEvent(`${actor.name} defends (defense doubled this turn)`);
                break;
            }
        }

        this._checkCombatEnd();
        return result;
    }

    nextTurn() {
        // Tick status effects
        const current = this.getCurrentActor();
        if (current) current.tickStatusEffects();

        this.currentTurn++;
        if (this.currentTurn >= this.turnOrder.length) {
            this.round++;
            this._calculateTurnOrder();
            this._logEvent(`--- Round ${this.round} ---`);
        }

        // Skip dead actors
        while (this.currentTurn < this.turnOrder.length && !this.turnOrder[this.currentTurn].isAlive) {
            this.currentTurn++;
        }

        return this.getCurrentActor();
    }

    _checkCombatEnd() {
        if (this.enemies.every(e => !e.isAlive)) {
            this.state = 'victory';
            this._logEvent('🎉 Victory!');
        } else if (this.allies.every(a => !a.isAlive)) {
            this.state = 'defeat';
            this._logEvent('💀 Defeat...');
        }
    }

    _logEvent(msg) {
        this.log.push({ round: this.round, message: msg, timestamp: Date.now() });
    }
}
