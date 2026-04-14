import { XP_PER_KILL, BASE_XP_PER_LEVEL } from '../config.js';

export class ProgressionSystem {
    constructor(scene) {
        this.scene = scene;
        this.level = 1;
        this.xp = 0;
        this.xpToNextLevel = BASE_XP_PER_LEVEL;
        this.unlockedDungeons = new Set(['Forest']);
    }

    update(time, delta) {
        // Check for level up
        this.checkLevelUp();
    }

    addXP(amount) {
        if (!this.scene.hero) return;
        
        this.xp += amount;
        this.scene.hero.xp += amount;
        
        // Check if hero can level up
        this.checkLevelUp();
    }

    checkLevelUp() {
        if (!this.scene.hero) return;

        while (this.scene.hero.xp >= this.scene.hero.xpToNextLevel) {
            this.levelUp();
        }
    }

    levelUp() {
        if (!this.scene.hero) return;

        const excessXP = this.scene.hero.xp - this.scene.hero.xpToNextLevel;
        
        this.scene.hero.level++;
        this.level = this.scene.hero.level;
        
        // Increase stats on level up
        this.scene.hero.maxHp += 10;
        this.scene.hero.currentHp = this.scene.hero.maxHp;
        this.scene.hero.attack += 2;
        this.scene.hero.defense += 1;
        this.scene.hero.speed += 0.5;
        
        // Calculate next level XP requirement (increases exponentially)
        this.scene.hero.xpToNextLevel = Math.floor(BASE_XP_PER_LEVEL * Math.pow(1.2, this.scene.hero.level - 1));
        this.scene.hero.xp = excessXP;
        
        // Check for dungeon unlocks
        this.checkDungeonUnlocks();
        
        console.log(`Level Up! Now level ${this.scene.hero.level}`);
    }

    checkDungeonUnlocks() {
        if (this.level >= 5 && !this.unlockedDungeons.has('Caves')) {
            this.unlockedDungeons.add('Caves');
            console.log('Caves dungeon unlocked!');
        }
        
        if (this.level >= 10 && !this.unlockedDungeons.has('Ruins')) {
            this.unlockedDungeons.add('Ruins');
            console.log('Ancient Ruins dungeon unlocked!');
        }
        
        if (this.level >= 15 && !this.unlockedDungeons.has('Tower')) {
            this.unlockedDungeons.add('Tower');
            console.log('Wizard Tower dungeon unlocked!');
        }
    }

    updateDungeonProgress() {
        // Update dungeon progress based on current level and achievements
        this.checkDungeonUnlocks();
    }

    getCurrentLevel() {
        return this.level;
    }

    getXPProgress() {
        if (!this.scene.hero) return { current: 0, required: 1, percent: 0 };
        
        const percent = (this.scene.hero.xp / this.scene.hero.xpToNextLevel) * 100;
        return {
            current: this.scene.hero.xp,
            required: this.scene.hero.xpToNextLevel,
            percent: Math.min(100, percent)
        };
    }

    getUnlockedDungeons() {
        return Array.from(this.unlockedDungeons);
    }
}