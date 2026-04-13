/**
 * GORVAX TEMPLATE — Progression System (XP & Levels)
 *
 * Features:
 * - XP curve with configurable scaling
 * - Level-up with stat growth
 * - Skill points allocation
 * - Prestige/rebirth system
 * - Milestone rewards
 */

class ProgressionSystem {
    constructor(config = {}) {
        this.level = 1;
        this.xp = 0;
        this.totalXp = 0;
        this.maxLevel = config.maxLevel || 100;
        this.baseXp = config.baseXp || 100;
        this.scaleFactor = config.scaleFactor || 1.5;
        this.skillPoints = 0;
        this.stats = {
            strength: 10,
            agility: 10,
            intelligence: 10,
            vitality: 10,
        };
        this.statGrowth = config.statGrowth || {
            strength: 2,
            agility: 2,
            intelligence: 2,
            vitality: 3,
        };
        this.milestones = config.milestones || {
            10: { reward: 'skill_unlock', data: 'double_strike' },
            25: { reward: 'title', data: 'Veteran' },
            50: { reward: 'skill_unlock', data: 'ultimate' },
            100: { reward: 'prestige_unlock', data: null },
        };
        this.prestigeLevel = 0;
        this.listeners = [];
    }

    xpForLevel(level) {
        return Math.floor(this.baseXp * Math.pow(level, this.scaleFactor));
    }

    xpToNextLevel() {
        return this.xpForLevel(this.level) - this.xp;
    }

    xpProgress() {
        const required = this.xpForLevel(this.level);
        return required > 0 ? this.xp / required : 1;
    }

    addXp(amount) {
        if (this.level >= this.maxLevel) return [];

        const prestigeBonus = 1 + this.prestigeLevel * 0.1;
        amount = Math.floor(amount * prestigeBonus);
        this.xp += amount;
        this.totalXp += amount;

        const levelsGained = [];
        while (this.xp >= this.xpForLevel(this.level) && this.level < this.maxLevel) {
            this.xp -= this.xpForLevel(this.level);
            this.level++;
            this.skillPoints += 1;
            this._applyStatGrowth();
            levelsGained.push(this.level);

            this._notify('level_up', { level: this.level, stats: { ...this.stats } });

            // Check milestones
            if (this.milestones[this.level]) {
                this._notify('milestone', {
                    level: this.level,
                    ...this.milestones[this.level],
                });
            }
        }

        return levelsGained;
    }

    _applyStatGrowth() {
        for (const [stat, growth] of Object.entries(this.statGrowth)) {
            if (this.stats[stat] !== undefined) {
                this.stats[stat] += growth;
            }
        }
    }

    allocateSkillPoint(stat) {
        if (this.skillPoints <= 0) return false;
        if (this.stats[stat] === undefined) return false;
        this.stats[stat] += 1;
        this.skillPoints--;
        this._notify('skill_allocated', { stat, value: this.stats[stat] });
        return true;
    }

    prestige() {
        if (this.level < this.maxLevel) return false;
        this.prestigeLevel++;
        this.level = 1;
        this.xp = 0;
        this.skillPoints = this.prestigeLevel * 5; // bonus skill points
        // Reset stats with prestige bonus
        for (const stat of Object.keys(this.stats)) {
            this.stats[stat] = 10 + this.prestigeLevel * 2;
        }
        this._notify('prestige', { prestigeLevel: this.prestigeLevel });
        return true;
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }

    toJSON() {
        return {
            level: this.level,
            xp: this.xp,
            totalXp: this.totalXp,
            skillPoints: this.skillPoints,
            stats: { ...this.stats },
            prestigeLevel: this.prestigeLevel,
        };
    }

    static fromJSON(data, config = {}) {
        const sys = new ProgressionSystem(config);
        Object.assign(sys, data);
        sys.stats = { ...data.stats };
        return sys;
    }
}
