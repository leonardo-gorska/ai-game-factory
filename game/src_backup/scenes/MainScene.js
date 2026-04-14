import { HERO_BASE_HP, DUNGEON_FLOORS } from '../config.js';
import { Hero } from '../entities/Hero.js';
import { CombatSystem } from '../systems/CombatSystem.js';
import { EconomySystem } from '../systems/EconomySystem.js';
import { ProgressionSystem } from '../systems/ProgressionSystem.js';
import { EnemySpawner } from '../systems/EnemySpawner.js';
import { Enemy } from '../entities/Enemy.js';
import { UpgradeSystem } from '../systems/UpgradeSystem.js';
export class MainScene extends Phaser.Scene {
    constructor() {
        super({ key: 'MainScene' });
        this.hero = null;
        this.combat = null;
        this.economy = null;
        this.progression = null;
        this.enemySpawner = null;
        this.upgradeSystem = null;
        this.dungeonFloors = DUNGEON_FLOORS;
    }

    create() {
        console.log('MainScene created');
        
        // Create hero
        this.hero = new Hero(this, 400, 300);
        
        // Initialize systems
        this.combat = new CombatSystem(this);
        this.economy = new EconomySystem(this);
        this.progression = new ProgressionSystem(this);
        this.enemySpawner = new EnemySpawner(this);
        this.upgradeSystem = new UpgradeSystem(this);
        
        // Start systems
        this.economy.initialize();
        this.enemySpawner.start();
        
        // Start first dungeon
        this.progression.startDungeon();
    }

    update(time, delta) {
        if (this.enemySpawner) {
            this.enemySpawner.update();
        }
        if (this.upgradeSystem) {
            this.upgradeSystem.update();
        }
    }
}