import { COMBAT_INTERVAL } from '../config.js';

export class CombatSystem {
    constructor(scene) {
        this.scene = scene;
        this.lastCombatTime = 0;
        this.isInCombat = false;
        this.currentEnemy = null;
    }

    update(time, delta) {
        if (time - this.lastCombatTime > COMBAT_INTERVAL && !this.isInCombat) {
            this.startCombat();
            this.lastCombatTime = time;
        }

        if (this.isInCombat) {
            this.processCombat();
        }
    }

    startCombat() {
        this.isInCombat = true;
        // Combat logic goes here
    }

    processCombat() {
        if (!this.scene.hero || !this.currentEnemy) {
            this.isInCombat = false;
            return;
        }

        // Hero attacks enemy
        const heroDamage = this.calculateDamage(this.scene.hero.attack, this.currentEnemy.defense);
        this.currentEnemy.currentHp -= heroDamage;

        // Enemy attacks hero if still alive
        if (this.currentEnemy.currentHp > 0) {
            const enemyDamage = this.calculateDamage(this.currentEnemy.attack, this.scene.hero.defense);
            this.scene.hero.currentHp -= enemyDamage;
        }

        // Check if combat is over
        if (this.currentEnemy.currentHp <= 0 || this.scene.hero.currentHp <= 0) {
            this.endCombat();
        }
    }

    calculateDamage(attack, defense) {
        // Damage formula: max(1, ATK - (DEF * 0.5))
        const calculatedDamage = attack - (defense * 0.5);
        return Math.max(1, Math.floor(calculatedDamage));
    }

    endCombat() {
        this.isInCombat = false;
        this.currentEnemy = null;
        
        // Handle rewards if hero won
        if (this.scene.hero.currentHp > 0 && this.scene.economy) {
            this.scene.economy.addGold(this.currentEnemy?.goldValue || 0);
            this.scene.progression?.addXP(this.currentEnemy?.xpValue || 0);
        }
    }

    setCurrentEnemy(enemy) {
        this.currentEnemy = enemy;
    }
}