import { DUNGEON_FLOORS, SPAWN_INTERVAL } from '../config.js';

export class EnemySpawner {
    constructor(scene) {
        this.scene = scene;
        this.spawnTimer = null;
        this.enemies = [];
        this.isSpawning = false;
    }

    start() {
        if (this.isSpawning) return;
        
        this.isSpawning = true;
        this.spawnTimer = this.scene.time.addEvent({
            delay: SPAWN_INTERVAL,
            callback: this.spawnEnemy,
            callbackScope: this,
            loop: true
        });
        
        // Spawn initial enemy
        this.spawnEnemy();
    }

    stop() {
        if (this.spawnTimer) {
            this.spawnTimer.remove();
            this.spawnTimer = null;
        }
        this.isSpawning = false;
    }

    spawnEnemy() {
        const screenWidth = this.scene.cameras.main.width;
        const screenHeight = this.scene.cameras.main.height;
        
        // Random Y position between 100 and 500
        const randomY = Phaser.Math.Between(100, 500);
        
        // Random enemy type from DUNGEON_FLOORS
        const randomEnemyIndex = Phaser.Math.Between(0, DUNGEON_FLOORS.length - 1);
        const enemyData = DUNGEON_FLOORS[randomEnemyIndex];
        
        // Create enemy sprite (spawn from right side)
        const enemy = this.scene.add.sprite(screenWidth + 50, randomY, `enemy${randomEnemyIndex + 1}`);
        enemy.setData('enemyData', { ...enemyData, currentHp: enemyData.hp });
        
        this.enemies.push(enemy);
        
        console.log(`Spawned ${enemyData.name} at position (${screenWidth + 50}, ${randomY})`);
    }

    destroyEnemy(enemy) {
        const index = this.enemies.indexOf(enemy);
        if (index > -1) {
            this.enemies.splice(index, 1);
        }
        enemy.destroy();
    }

    cleanup() {
        this.stop();
        this.enemies.forEach(enemy => enemy.destroy());
        this.enemies = [];
    }
}