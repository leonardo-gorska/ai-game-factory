/**
 * GORVAX GAME FACTORY — Entry Point
 * Bootstraps the Phaser game. Part of the project scaffold.
 */
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
        autoCenter: Phaser.Scale.CENTER_BOTH,
    },
};

const game = new Phaser.Game(config);
export default game;
