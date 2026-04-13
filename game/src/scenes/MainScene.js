import Phaser from 'phaser';
import { HERO_BASE_HP, HERO_BASE_ATK, HERO_BASE_DEF, HERO_BASE_SPD, GOLD_PER_SECOND } from '../config.js';
import { Hero } from '../entities/Hero.js';
import { CombatSystem } from '../systems/CombatSystem.js';
import { EconomySystem } from '../systems/EconomySystem.js';
import { ProgressionSystem } from '../systems/ProgressionSystem.js';
import { EnemySpawner } from '../systems/EnemySpawner.js';
import { Enemy } from '../entities/Enemy.js';
import { UpgradeSystem } from '../systems/UpgradeSystem.js';
export class MainScene extends Phaser.Scene {
    constructor() {
        super('MainScene');
    }

    create() {
        this.hero = new Hero(this, 400, 300);
        this.add.existing(this.hero);

        this.combat = new CombatSystem(this);
        this.economy = new EconomySystem(this);
        this.progression = new ProgressionSystem(this);
        this.enemySpawner = new EnemySpawner(this);
        this.upgradeSystem = new UpgradeSystem(this);

        this.enemySpawner.start();

        // Gold display
        this.goldText = this.add.text(20, 20, 'Gold: 0', { fontSize: '24px', color: '#ffd700' });
        this.levelText = this.add.text(20, 50, 'Level: 1', { fontSize: '24px', color: '#ffffff' });
        this.xpText = this.add.text(20, 80, 'XP: 0/100', { fontSize: '24px', color: '#88ff88' });
    }

    update(time, delta) {
        this.combat.update(time, delta);
        this.economy.update(time, delta);
        this.progression.update(time, delta);
        this.upgradeSystem.update();

        // Update UI
        if (this.economy) {
            this.goldText.setText(`Gold: ${Math.floor(this.economy.gold)}`);
        }
        if (this.progression) {
            this.levelText.setText(`Level: ${this.progression.level}`);
            this.xpText.setText(`XP: ${Math.floor(this.progression.xp)}/${this.progression.xpToNextLevel}`);
        }
    }
}