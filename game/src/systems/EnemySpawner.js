import { DUNGEON_ENEMIES } from '../config.js';
import { Enemy } from '../entities/Enemy.js';
export class EnemySpawner {
    constructor(scene) {
        this.scene = scene;
        this.enemies = [];
        this.spawnTimer = null;
        this.spawnInterval = 3000; // 3 seconds
    }
    start() {
        this.spawnTimer = this.scene.time.addEvent({
            delay: this.spawnInterval,
            callback: this.spawnEnemy,
            callbackScope: this,
            loop: true
        });
        this.spawnEnemy();
    }
    stop() {
        if (this.spawnTimer) {
            this.spawnTimer.remove();
            this.spawnTimer = null;
        }
    }
    spawnEnemy() {
        const x = Phaser.Math.Between(100, 700);
        const y = Phaser.Math.Between(100, 500);
        const enemy = new Enemy(this.scene, x, y);
        this.enemies.push(enemy);
    }
    removeEnemy(enemy) {
        const index = this.enemies.indexOf(enemy);
        if (index > -1) {
            this.enemies.splice(index, 1);
        }
    }
    getRandomEnemy() {
        if (this.enemies.length === 0) return null;
        return this.enemies[Phaser.Math.Between(0, this.enemies.length - 1)];
    }
}