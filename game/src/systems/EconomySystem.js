import { GOLD_PER_SECOND } from '../config.js';

export class EconomySystem {
    constructor(scene) {
        this.scene = scene;
        this.gold = 0;
        this.gems = 0;
        this.lastGoldTime = 0;
    }

    update(time, delta) {
        // Generate gold over time
        if (this.lastGoldTime === 0) {
            this.lastGoldTime = time;
        }
        
        const elapsedSeconds = (time - this.lastGoldTime) / 1000;
        if (elapsedSeconds >= 1) {
            this.addGold(GOLD_PER_SECOND * elapsedSeconds);
            this.lastGoldTime = time;
        }
    }

    addGold(amount) {
        this.gold += amount;
        return this.gold;
    }

    spendGold(amount) {
        if (this.gold >= amount) {
            this.gold -= amount;
            return true;
        }
        return false;
    }

    addGems(amount) {
        this.gems += amount;
        return this.gems;
    }

    spendGems(amount) {
        if (this.gems >= amount) {
            this.gems -= amount;
            return true;
        }
        return false;
    }
}