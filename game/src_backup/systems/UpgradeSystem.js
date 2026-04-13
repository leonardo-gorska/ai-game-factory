import { 
    UPGRADE_BASE_COST_ATK, 
    UPGRADE_BASE_COST_DEF, 
    UPGRADE_BASE_COST_HP, 
    UPGRADE_ATK_INCREASE, 
    UPGRADE_DEF_INCREASE, 
    UPGRADE_HP_INCREASE, 
    UPGRADE_COST_MULTIPLIER 
} from '../config.js';

export class UpgradeSystem {
    constructor(scene) {
        this.scene = scene;
        this.currentStats = {
            atk: 10,
            def: 5,
            hp: 100
        };
        this.upgradeCosts = {
            atk: UPGRADE_BASE_COST_ATK,
            def: UPGRADE_BASE_COST_DEF,
            hp: UPGRADE_BASE_COST_HP
        };
        this.upgradeButtons = {};
        this.createUI();
    }

    createUI() {
        const buttonWidth = 250;
        const buttonHeight = 80;
        const buttonSpacing = 20;
        const totalWidth = buttonWidth * 3 + buttonSpacing * 2;
        const startX = (800 - totalWidth) / 2 + buttonWidth / 2;
        const y = 550;

        // ATK Upgrade Button (Red)
        this.upgradeButtons.atk = this.scene.add.rectangle(startX, y, buttonWidth, buttonHeight, 0xff4444)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgrade('atk'));
        
        // DEF Upgrade Button (Blue)
        this.upgradeButtons.def = this.scene.add.rectangle(startX + buttonWidth + buttonSpacing, y, buttonWidth, buttonHeight, 0x4444ff)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgrade('def'));
        
        // HP Upgrade Button (Green)
        this.upgradeButtons.hp = this.scene.add.rectangle(startX + (buttonWidth + buttonSpacing) * 2, y, buttonWidth, buttonHeight, 0x44ff44)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgrade('hp'));

        // Button labels
        this.updateButtonText();
    }

    updateButtonText() {
        const buttonTextStyle = {
            fontSize: '16px',
            fill: '#ffffff',
            align: 'center'
        };

        // Remove existing text if any
        if (this.buttonTexts) {
            this.buttonTexts.forEach(text => text.destroy());
        }

        this.buttonTexts = [];

        // ATK Button Text
        const atkText = this.scene.add.text(
            this.upgradeButtons.atk.x,
            this.upgradeButtons.atk.y - 10,
            `ATK: ${this.currentStats.atk}\nCost: ${this.upgradeCosts.atk}g`,
            buttonTextStyle
        ).setOrigin(0.5);

        // DEF Button Text
        const defText = this.scene.add.text(
            this.upgradeButtons.def.x,
            this.upgradeButtons.def.y - 10,
            `DEF: ${this.currentStats.def}\nCost: ${this.upgradeCosts.def}g`,
            buttonTextStyle
        ).setOrigin(0.5);

        // HP Button Text
        const hpText = this.scene.add.text(
            this.upgradeButtons.hp.x,
            this.upgradeButtons.hp.y - 10,
            `HP: ${this.currentStats.hp}\nCost: ${this.upgradeCosts.hp}g`,
            buttonTextStyle
        ).setOrigin(0.5);

        this.buttonTexts.push(atkText, defText, hpText);

        // Update button colors based on affordability
        this.updateButtonStates();
    }

    updateButtonStates() {
        const currentGold = this.scene.economy ? this.scene.economy.gold : 0;
        
        this.upgradeButtons.atk.setAlpha(currentGold >= this.upgradeCosts.atk ? 1 : 0.5);
        this.upgradeButtons.def.setAlpha(currentGold >= this.upgradeCosts.def ? 1 : 0.5);
        this.upgradeButtons.hp.setAlpha(currentGold >= this.upgradeCosts.hp ? 1 : 0.5);
    }

    upgrade(statType) {
        if (!this.scene.economy) return;
        
        const cost = this.upgradeCosts[statType];
        
        if (this.scene.economy.gold >= cost) {
            // Deduct gold
            this.scene.economy.gold -= cost;
            
            // Increase stat
            switch (statType) {
                case 'atk':
                    this.currentStats.atk += UPGRADE_ATK_INCREASE;
                    if (this.scene.hero) this.scene.hero.attack = this.currentStats.atk;
                    break;
                case 'def':
                    this.currentStats.def += UPGRADE_DEF_INCREASE;
                    if (this.scene.hero) this.scene.hero.defense = this.currentStats.def;
                    break;
                case 'hp':
                    this.currentStats.hp += UPGRADE_HP_INCREASE;
                    if (this.scene.hero) {
                        this.scene.hero.maxHp = this.currentStats.hp;
                        this.scene.hero.currentHp = this.currentStats.hp;
                    }
                    break;
            }
            
            // Update cost (round to nearest 5)
            this.upgradeCosts[statType] = Math.round(this.upgradeCosts[statType] * UPGRADE_COST_MULTIPLIER / 5) * 5;
            
            // Update UI
            this.updateButtonText();
            
            // Update economy display if available
            if (this.scene.economy.updateResourceDisplay) {
                this.scene.economy.updateResourceDisplay();
            }
            
            console.log(`Upgraded ${statType.toUpperCase()} to ${this.currentStats[statType]}. New cost: ${this.upgradeCosts[statType]}g`);
        }
    }

    update() {
        this.updateButtonStates();
    }
}