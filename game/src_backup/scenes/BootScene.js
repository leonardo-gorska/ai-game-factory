import Phaser from 'phaser';

/**
 * BootScene — Generates procedural placeholder textures
 * so the game works without external asset files.
 */
export class BootScene extends Phaser.Scene {
    constructor() {
        super('BootScene');
    }

    preload() {
        // Generate placeholder textures procedurally (no external assets needed)
        this.createPlaceholder('hero', 0x44aaff, 32, 32);
        this.createPlaceholder('enemy1', 0xff4444, 28, 28);
        this.createPlaceholder('enemy2', 0xff6644, 28, 28);
        this.createPlaceholder('enemy3', 0xff8844, 28, 28);
        this.createPlaceholder('enemy4', 0xffaa44, 28, 28);
        this.createPlaceholder('enemy5', 0xffcc44, 28, 28);
    }

    createPlaceholder(key, color, w, h) {
        if (this.textures.exists(key)) return;
        const g = this.add.graphics();
        g.fillStyle(color, 1);
        g.fillRoundedRect(0, 0, w, h, 4);
        g.generateTexture(key, w, h);
        g.destroy();
    }

    create() {
        this.scene.start('MainScene');
    }
}
