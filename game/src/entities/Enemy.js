import { GOBLIN_HP, GOBLIN_ATK, GOBLIN_DEF, GOBLIN_SPD, GOBLIN_GOLD, GOBLIN_XP } from '../config.js';

export class Enemy extends Phaser.GameObjects.Sprite {
    constructor(scene, x, y, enemyType = 'goblin') {
        super(scene, x, y, 'enemy1');
        
        // Set enemy stats based on type
        this.enemyType = enemyType;
        this.maxHp = GOBLIN_HP;
        this.currentHp = GOBLIN_HP;
        this.attack = GOBLIN_ATK;
        this.defense = GOBLIN_DEF;
        this.speed = GOBLIN_SPD;
        this.goldValue = GOBLIN_GOLD;
        this.xpValue = GOBLIN_XP;
        
        this.setOrigin(0.5, 0.5);
        this.setScale(0.8);
        
        // Create HP bar
        this.createHpBar();
        
        scene.add.existing(this);
    }
    
    createHpBar() {
        // HP bar background (red)
        this.hpBarBg = this.scene.add.graphics();
        this.hpBarBg.fillStyle(0xff0000, 0.8);
        this.hpBarBg.fillRect(-16, -25, 32, 4);
        this.hpBarBg.setDepth(1);
        
        // HP bar fill (green)
        this.hpBarFill = this.scene.add.graphics();
        this.hpBarFill.fillStyle(0x00ff00, 0.8);
        this.hpBarFill.fillRect(-16, -25, 32, 4);
        this.hpBarFill.setDepth(2);
        
        // Add HP bars as children so they move with the enemy
        this.add(this.hpBarBg);
        this.add(this.hpBarFill);
        
        this.updateHpBar();
    }
    
    updateHpBar() {
        const hpPercent = this.currentHp / this.maxHp;
        this.hpBarFill.clear();
        this.hpBarFill.fillStyle(0x00ff00, 0.8);
        this.hpBarFill.fillRect(-16, -25, 32 * hpPercent, 4);
    }
    
    takeDamage(amount) {
        this.currentHp = Math.max(0, this.currentHp - amount);
        this.updateHpBar();
        
        // Show damage text
        this.showDamageText(amount);
        
        if (this.currentHp <= 0) {
            this.die();
            return true; // Enemy died
        }
        return false; // Enemy still alive
    }
    
    showDamageText(amount) {
        const damageText = this.scene.add.text(this.x, this.y - 40, `-${amount}`, {
            fontSize: '16px',
            fill: '#ff4444',
            fontFamily: 'Arial',
            fontWeight: 'bold'
        });
        damageText.setOrigin(0.5, 0.5);
        
        // Animate damage text
        this.scene.tweens.add({
            targets: damageText,
            y: this.y - 60,
            alpha: 0,
            duration: 1000,
            ease: 'Power2',
            onComplete: () => {
                damageText.destroy();
            }
        });
    }
    
    die() {
        // Show gold drop text
        this.showGoldText(this.goldValue);
        
        // Remove from scene
        this.hpBarBg.destroy();
        this.hpBarFill.destroy();
        this.destroy();
        
        // Notify systems
        if (this.scene.economy) {
            this.scene.economy.addGold(this.goldValue);
        }
        if (this.scene.progression) {
            this.scene.progression.addXP(this.xpValue);
        }
        if (this.scene.combat && this.scene.combat.currentEnemy === this) {
            this.scene.combat.endCombat();
        }
    }
    
    showGoldText(amount) {
        const goldText = this.scene.add.text(this.x, this.y - 20, `+${amount} Gold`, {
            fontSize: '14px',
            fill: '#ffd700',
            fontFamily: 'Arial',
            fontWeight: 'bold'
        });
        goldText.setOrigin(0.5, 0.5);
        
        // Animate gold text
        this.scene.tweens.add({
            targets: goldText,
            y: this.y - 40,
            alpha: 0,
            duration: 1500,
            ease: 'Power2',
            onComplete: () => {
                goldText.destroy();
            }
        });
    }
}