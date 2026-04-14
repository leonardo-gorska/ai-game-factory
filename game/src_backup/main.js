import Phaser from 'phaser';
import { BootScene } from './scenes/BootScene.js';
import { MainScene } from './scenes/MainScene.js';
const config = {
    type: Phaser.AUTO,
    parent: 'game-container',
    width: 800,
    height: 600,
    backgroundColor: '#0a0a1a',
    physics: {
        default: 'arcade',
        arcade: { gravity: { x: 0, y: 0 }, debug: false },
    },
    scene: [BootScene, MainScene],
    scale: {
        mode: Phaser.Scale.FIT,
        parent: 'game-container',
        autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    locale: 'en-US',
    fps: {
        min: 30,
        target: 60,
        forceStep: true,
    },
    render: {
        pixelArt: true,
        roundPixels: true,
    },
};
const game = new Phaser.Game(config);
