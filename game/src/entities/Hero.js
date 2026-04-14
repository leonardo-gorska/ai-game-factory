import { HERO_BASE_HP, HERO_BASE_ATK, HERO_BASE_DEF, HERO_BASE_SPD, BASE_XP_PER_LEVEL } from '../config.js';

export class Hero extends Phaser.GameObjects.Sprite {
    constructor(scene, x, y) {
        super(scene, x, y, 'hero');
        this.level = 1;
        this.maxHp = HERO_BASE_HP;
        this.currentHp = HERO_BASE_HP;
        this.attack = HERO_BASE_ATK;
        this.defense = HERO_BASE_DEF;
        this.speed = HERO_BASE_SPD;
        this.xp = 0;
        this.xpToNextLevel = BASE_XP_PER_LEVEL;
        this.setOrigin(0.5, 0.5);
        this.setScale(1.5);
    }

    addXP(amount) {
        this.xp += amount;
        return this.xp;
    }

    levelUp() {
        this.level++;
        this.maxHp += 10;
        this.currentHp = this.maxHp;
        this.attack += 2;
        this.defense += 1;
        this.speed += 0.5;
        
        // Exponential XP requirement growth
        this.xpToNextLevel = Math.floor(BASE_XP_PER_LEVEL * Math.pow(1.2, this.level - 1));
        
        return this.level;
    }

    getStats() {
        return {
            level: this.level,
            maxHp: this.maxHp,
            currentHp: this.currentHp,
            attack: this.attack,
            defense: this.defense,
            speed: this.speed,
            xp: this.xp,
            xpToNextLevel: this.xpToNextLevel
        };
    }

    isAlive() {
        return this.currentHp > 0;
    }

    takeDamage(damage) {
        const actualDamage = Math.max(0, damage - this.defense);
        this.currentHp -= actualDamage;
        return actualDamage;
    }

    heal(amount) {
        this.currentHp = Math.min(this.maxHp, this.currentHp + amount);
        return this.currentHp;
    }
}