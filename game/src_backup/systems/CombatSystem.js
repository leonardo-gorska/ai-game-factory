export class CombatSystem {
    constructor(scene) {
        this.scene = scene;
        this.isCombatActive = false;
        this.currentEnemy = null;
        this.attackTimer = null;
    }
    
    startCombat(floorIndex) {
        if (this.isCombatActive) return;
        
        this.isCombatActive = true;
        const enemyData = this.scene.dungeonFloors[floorIndex];
        
        // Create enemy sprite
        this.currentEnemy = this.scene.add.sprite(500, 300, 'enemy');
        this.currentEnemy.data = { ...enemyData, currentHp: enemyData.hp };
        
        // Start attack timer
        this.attackTimer = this.scene.time.addEvent({
            delay: this.scene.hero.getAttackSpeed(),
            callback: this.heroAttack,
            callbackScope: this,
            loop: true
        });
    }
    
    heroAttack() {
        if (!this.currentEnemy || !this.isCombatActive) return;
        
        const hero = this.scene.hero;
        const enemy = this.currentEnemy.data;
        
        // Calculate damage
        const damage = Math.max(1, hero.attack - enemy.def);
        enemy.currentHp -= damage;
        
        console.log(`Hero attacks for ${damage} damage! Enemy HP: ${enemy.currentHp}/${enemy.hp}`);
        
        // Check if enemy is defeated
        if (enemy.currentHp <= 0) {
            this.defeatEnemy();
        }
    }
    
    defeatEnemy() {
        if (!this.currentEnemy) return;
        
        const enemy = this.currentEnemy.data;
        
        // Reward player
        this.scene.economy.addGold(enemy.gold);
        this.scene.hero.addXP(enemy.xp);
        
        console.log(`Enemy defeated! Gained ${enemy.gold} gold and ${enemy.xp} XP`);
        
        // Clean up
        this.currentEnemy.destroy();
        this.currentEnemy = null;
        this.isCombatActive = false;
        
        if (this.attackTimer) {
            this.attackTimer.remove();
            this.attackTimer = null;
        }
    }
    
    stopCombat() {
        this.isCombatActive = false;
        
        if (this.currentEnemy) {
            this.currentEnemy.destroy();
            this.currentEnemy = null;
        }
        
        if (this.attackTimer) {
            this.attackTimer.remove();
            this.attackTimer = null;
        }
    }
}