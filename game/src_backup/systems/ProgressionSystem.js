export class ProgressionSystem {
    constructor(scene) {
        this.scene = scene;
        this.currentDungeon = 'Goblin Caves';
        this.currentFloor = 0;
        this.dungeonsCompleted = 0;
    }
    
    startDungeon() {
        console.log(`Starting ${this.currentDungeon} - Floor ${this.currentFloor + 1}`);
        this.scene.combat.startCombat(this.currentFloor);
    }
    
    completeFloor() {
        this.currentFloor++;
        
        if (this.currentFloor >= this.scene.dungeonFloors.length) {
            this.completeDungeon();
        } else {
            console.log(`Floor completed! Moving to floor ${this.currentFloor + 1}`);
            this.startDungeon();
        }
    }
    
    completeDungeon() {
        console.log(`Dungeon ${this.currentDungeon} completed!`);
        this.dungeonsCompleted++;
        this.currentFloor = 0;
        
        // Reward for dungeon completion
        const completionBonus = 50 + (this.dungeonsCompleted * 25);
        this.scene.economy.addGold(completionBonus);
        this.scene.hero.addXP(100);
        
        console.log(`Received ${completionBonus} gold and 100 XP for dungeon completion!`);
    }
    
    getCurrentProgress() {
        return {
            dungeon: this.currentDungeon,
            floor: this.currentFloor + 1,
            totalFloors: this.scene.dungeonFloors.length,
            dungeonsCompleted: this.dungeonsCompleted
        };
    }
}