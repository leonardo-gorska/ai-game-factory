import Phaser from 'phaser';
export class BootScene extends Phaser.Scene {
    constructor() {
        super('BootScene');
    }
    preload() {
        this.createPlaceholder('hero', 0x44aaff, 32, 32);
        this.createPlaceholder('enemy1', 0xff4444, 28, 28);
        this.createPlaceholder('enemy2', 0xff6644, 28, 28);
        this.createPlaceholder('enemy3', 0xff8844, 28, 28);
        this.createPlaceholder('enemy4', 0xffaa44, 28, 28);
        this.load.plugin('rexuiplugin', 'https://raw.githubusercontent.com/rexrainbow/phaser3-rex-plugins/master/templates/rexuiplugin.min.js', true);
    }
    
}
