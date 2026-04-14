import { GOLD_GENERATION_RATE, GOLD_GENERATION_INTERVAL } from '../config.js';

export class EconomySystem {
    constructor(scene) {
        this.scene = scene;
        this.gold = 0;
        this.gems = 0;
        this.goldGenerationTimer = null;
    }
    initialize() {
        this.goldGenerationTimer = this.scene.time.addEvent({
            delay: GOLD_GENERATION_INTERVAL, // 10 seconds
            callback: this.generateGold,
            callbackScope: this,
            loop: true
        });
        this.generateGold();
    }
    generateGold() {
        this.gold += GOLD_GENERATION_RATE;
        console.log(`Generated ${GOLD_GENERATION_RATE} gold.
`);
        if (this.gold >= 1000) {
            this.gold = 0;
        }
    }
    
}
