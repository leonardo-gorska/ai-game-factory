export class Hero extends Phaser.GameObjects.Sprite {
    constructor(scene, x, y) {
        super(scene, x, y, 'hero');
        
        this.scene = scene;
        this.level = 1;
        this.xp = 0;
        this.xpToNextLevel = 100;
        
        // Base stats
        this.maxHp = 100;
        this.currentHp = 100;
        this.attack = 10;
        this.defense = 5;
        this.speed = 3;
        
        scene.add.existing(this);
        this.setInteractive();
    }
    
    addXP(amount) {
        this.xp += amount;
        
        // Check for level up
        if (this.xp >= this.xpToNextLevel && this.level < 20) {
            this.levelUp();
        }
        
        return this.xp;
    }
    
    levelUp() {
        this.level++;
        this.xp -= this.xpToNextLevel;
        
        // Increase stats
        this.maxHp += 20;
        this.currentHp = this.maxHp;
        this.attack += 5;
        this.defense += 2;
        this.speed += 1;
        
        // Set next XP threshold (simplified for now)
        this.xpToNextLevel = 100 + (this.level * 50);
        
        console.log(`Hero leveled up to level ${this.level}!`);
    }
    
    getAttackSpeed() {
        return (10 / this.speed) * 1000; // Convert to milliseconds
    }
}