import { UPGRADE_BASE_ATK_COST, UPGRADE_ATK_COST_MULTIPLIER, UPGRADE_ATK_AMOUNT, UPGRADE_BASE_DEF_COST, UPGRADE_DEF_COST_MULTIPLIER, UPGRADE_DEF_AMOUNT, UPGRADE_BASE_HP_COST, UPGRADE_HP_COST_MULTIPLIER, UPGRADE_HP_AMOUNT } from '../config.js';

export class UpgradeSystem {
    constructor(scene) {
        this.scene = scene;
        this.atkLevel = 1;
        this.defLevel = 1;
        this.hpLevel = 1;
        this.buttons = [];
        this.texts = [];
        this.createUI();
    }

    createUI() {
        const buttonWidth = 200;
        const buttonHeight = 50;
        const buttonSpacing = 20;
        const startY = this.scene.cameras.main.height - buttonHeight - 20;
        
        // ATK Upgrade Button
        const atkButton = this.scene.add.rectangle(150, startY, buttonWidth, buttonHeight, 0x44aa44)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgradeStat('atk'));
        
        const atkText = this.scene.add.text(150, startY, `ATK: ${this.scene.hero.attack} (${this.getNextAtkCost()}g)`)
            .setOrigin(0.5)
            .setStyle({ fontSize: '16px', color: '#ffffff' });

        // DEF Upgrade Button
        const defButton = this.scene.add.rectangle(400, startY, buttonWidth, buttonHeight, 0x4444aa)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgradeStat('def'));
        
        const defText = this.scene.add.text(400, startY, `DEF: ${this.scene.hero.defense} (${this.getNextDefCost()}g)`)
            .setOrigin(0.5)
            .setStyle({ fontSize: '16px', color: '#ffffff' });

        // HP Upgrade Button
        const hpButton = this.scene.add.rectangle(650, startY, buttonWidth, buttonHeight, 0xaa4444)
            .setInteractive({ useHandCursor: true })
            .on('pointerdown', () => this.upgradeStat('hp'));
        
        const hpText = this.scene.add.text(650, startY, `HP: ${this.scene.hero.maxHp} (${this.getNextHpCost()}g)`)
            .setOrigin(0.5)
            .setStyle({ fontSize: '16px', color: '#ffffff' });

        this.buttons = [atkButton, defButton, hpButton];
        this.texts = [atkText, defText, hpText];
    }

    upgradeStat(statType) {
        if (!this.scene.hero || !this.scene.economy) return;

        let cost = 0;
        let canAfford = false;

        switch (statType) {
            case 'atk':
                cost = this.getNextAtkCost();
                canAfford = this.scene.economy.gold >= cost;
                if (canAfford) {
                    this.scene.economy.addGold(-cost);
                    this.scene.hero.attack += UPGRADE_ATK_AMOUNT;
                    this.atkLevel++;
                    this.showUpgradeEffect(this.buttons[0]);
                }
                break;
            case 'def':
                cost = this.getNextDefCost();
                canAfford = this.scene.economy.gold >= cost;
                if (canAfford) {
                    this.scene.economy.addGold(-cost);
                    this.scene.hero.defense += UPGRADE_DEF_AMOUNT;
                    this.defLevel++;
                    this.showUpgradeEffect(this.buttons[1]);
                }
                break;
            case 'hp':
                cost = this.getNextHpCost();
                canAfford = this.scene.economy.gold >= cost;
                if (canAfford) {
                    this.scene.economy.addGold(-cost);
                    this.scene.hero.maxHp += UPGRADE_HP_AMOUNT;
                    this.scene.hero.currentHp += UPGRADE_HP_AMOUNT;
                    this.hpLevel++;
                    this.showUpgradeEffect(this.buttons[2]);
                }
                break;
        }

        if (canAfford) {
            this.updateButtonTexts();
        }
    }

    getNextAtkCost() {
        return Math.floor(UPGRADE_BASE_ATK_COST * Math.pow(UPGRADE_ATK_COST_MULTIPLIER, this.atkLevel - 1));
    }

    getNextDefCost() {
        return Math.floor(UPGRADE_BASE_DEF_COST * Math.pow(UPGRADE_DEF_COST_MULTIPLIER, this.defLevel - 1));
    }

    getNextHpCost() {
        return Math.floor(UPGRADE_BASE_HP_COST * Math.pow(UPGRADE_HP_COST_MULTIPLIER, this.hpLevel - 1));
    }

    updateButtonTexts() {
        if (this.texts[0]) {
            this.texts[0].setText(`ATK: ${this.scene.hero.attack} (${this.getNextAtkCost()}g)`);
        }
        if (this.texts[1]) {
            this.texts[1].setText(`DEF: ${this.scene.hero.defense} (${this.getNextDefCost()}g)`);
        }
        if (this.texts[2]) {
            this.texts[2].setText(`HP: ${this.scene.hero.maxHp} (${this.getNextHpCost()}g)`);
        }
    }

    showUpgradeEffect(button) {
        // Visual feedback for upgrade
        this.scene.tweens.add({
            targets: button,
            scaleX: 1.2,
            scaleY: 1.2,
            duration: 100,
            yoyo: true,
            ease: 'Power2'
        });
    }

    update() {
        // Update button states based on affordability
        if (this.scene.economy) {
            this.buttons.forEach((button, index) => {
                let canAfford = false;
                switch (index) {
                    case 0: canAfford = this.scene.economy.gold >= this.getNextAtkCost(); break;
                    case 1: canAfford = this.scene.economy.gold >= this.getNextDefCost(); break;
                    case 2: canAfford = this.scene.economy.gold >= this.getNextHpCost(); break;
                }
                button.setAlpha(canAfford ? 1 : 0.6);
            });
        }
    }
}