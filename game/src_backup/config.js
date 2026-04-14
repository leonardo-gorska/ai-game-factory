// Hero constants
export const HERO_BASE_HP = 100;
export const HERO_BASE_ATK = 10;
export const HERO_BASE_DEF = 5;
export const HERO_BASE_SPD = 3;
export const HERO_XP_PER_LEVEL = 100;
export const HERO_MAX_LEVEL = 20;

// Economy constants
export const GOLD_GENERATION_RATE = 1; // gold per 10 seconds
export const GOLD_GENERATION_INTERVAL = 10000; // 10 seconds in milliseconds

// Combat constants
export const XP_PER_KILL = 10;

// Dungeon constants - Goblin Caves
export const DUNGEON_FLOORS = [
    { name: 'Goblin', hp: 50, atk: 5, def: 2, xp: 10, gold: 5 },
    { name: 'Goblin Warrior', hp: 70, atk: 7, def: 3, xp: 15, gold: 8 },
    { name: 'Goblin Archer', hp: 60, atk: 9, def: 1, xp: 20, gold: 10 },
    { name: 'Goblin Shaman', hp: 80, atk: 8, def: 4, xp: 25, gold: 12 },
    { name: 'Goblin Chief', hp: 120, atk: 12, def: 6, xp: 50, gold: 20 }
];

// Level progression thresholds
export const LEVEL_THRESHOLDS = [
    100,   // Level 2
    250,   // Level 3
    450,   // Level 4
    700    // Level 5
];

// ── Auto-added by roadmap ──
export const SPAWN_INTERVAL = 3000; // 3 seconds in milliseconds

// ── Auto-added by roadmap ──
export const UPGRADE_BASE_COST_ATK = 50;

export const UPGRADE_BASE_COST_DEF = 50;

export const UPGRADE_BASE_COST_HP = 50;

export const UPGRADE_ATK_INCREASE = 2;

export const UPGRADE_DEF_INCREASE = 1;

export const UPGRADE_HP_INCREASE = 10;

export const UPGRADE_COST_MULTIPLIER = 1.25;
