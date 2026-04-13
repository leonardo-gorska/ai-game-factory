export class Enemy extends Phaser.GameObjects.Container {
    constructor(scene, x, y, enemyData) {
        super(scene, x, y);
        this.scene = scene;
        this.enemyData = enemyData;
        
        // Create enemy sprite (green circle)
        this.sprite = scene.add.sprite(0, 0, 'enemy');
        this.add(this.sprite);
        
        // Create health bar background
        this.healthBarBg = scene.add.rectangle(0, -20, 40, 4, 0xff0000);
        this.healthBarBg.setOrigin(0.5, 0.5);
        this.add(this.healthBarBg);
        
        // Create health bar fill
        this.healthBarFill = scene.add.rectangle(0, -20, 40, 4, 0x00ff00);
        this.healthBarFill.setOrigin(0.5, 0.5);
        this.add(this.healthBarFill);
        
        // Initialize enemy stats
        this.maxHp = enemyData.hp;
        this.currentHp = enemyData.hp;
        this.attack = enemyData.atk;
        this.defense = enemyData.def;
        this.attackSpeed = enemyData.attackSpeed || 1500;
        
        // Update health bar
        this.updateHealthBar();
        
        scene.add.existing(this);
    }
    
    takeDamage(amount) {
        const actualDamage = Math.max(0, amount - this.defense);
        this.currentHp -= actualDamage;
        this.updateHealthBar();
        
        // Show damage text
        if (actualDamage > 0) {
            const damageText = this.scene.add.text(this.x, this.y - 40, `-${actualDamage}`, {
                fontSize: '16px',
                fill: '#ff4444',
                stroke: '#000',
                strokeThickness: 2
            });
            damageText.setOrigin(0.5, 0.5);
            
            this.scene.tweens.add({
                targets: damageText,
                y: this.y - 60,
                alpha: 0,
                duration: 1000,
                onComplete: () => damageText.destroy()
            });
        }
        
        return actualDamage;
    }
    
    updateHealthBar() {
        const healthPercent = Math.max(0, this.currentHp / this.maxHp);
        this.healthBarFill.width = 40 * healthPercent;
        
        // Change color based on health
        if (healthPercent < 0.3) {
            this.healthBarFill.fillColor = 0xff0000; // Red
        } else if (healthPercent < 0.6) {
            this.healthBarFill.fillColor = 0xffff00; // Yellow
        } else {
            this.healthBarFill.fillColor = 0x00ff00; // Green
        }
    }
    
    isDead() {
        return this.currentHp <= 0;
    }
    
    destroy() {
        // Clean up before destruction
        if (this.healthBarBg) this.healthBarBg.destroy();
        if (this.healthBarFill) this.healthBarFill.destroy();
        if (this.sprite) this.sprite.destroy();
        super.destroy();
    }
}