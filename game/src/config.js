// Hero Base Stats
export const HERO_BASE_HP = 100;
export const HERO_BASE_ATK = 10;
export const HERO_BASE_DEF = 5;
export const HERO_BASE_SPD = 3;

// Economy
export const GOLD_PER_SECOND = 1;
export const OFFLINE_GOLD_RATE = 0.5;

// Progression
export const XP_PER_KILL = 10;
export const BASE_XP_PER_LEVEL = 100;

// Combat
export const COMBAT_INTERVAL = 3000; // 3 seconds

// Dungeon 1: Goblin Caves
// Floor 1: Goblin
export const GOBLIN_HP = 50;
export const GOBLIN_ATK = 5;
export const GOBLIN_DEF = 2;
export const GOBLIN_SPD = 2;
export const GOBLIN_GOLD = 5;
export const GOBLIN_XP = 10;

// Floor 2: Goblin Warrior
export const GOBLIN_WARRIOR_HP = 70;
export const GOBLIN_WARRIOR_ATK = 7;
export const GOBLIN_WARRIOR_DEF = 3;
export const GOBLIN_WARRIOR_SPD = 2;
export const GOBLIN_WARRIOR_GOLD = 7;
export const GOBLIN_WARRIOR_XP = 15;

// Floor 3: Goblin Archer
export const GOBLIN_ARCHER_HP = 60;
export const GOBLIN_ARCHER_ATK = 8;
export const GOBLIN_ARCHER_DEF = 1;
export const GOBLIN_ARCHER_SPD = 4;
export const GOBLIN_ARCHER_GOLD = 8;
export const GOBLIN_ARCHER_XP = 20;

// Floor 4: Goblin Shaman
export const GOBLIN_SHAMAN_HP = 80;
export const GOBLIN_SHAMAN_ATK = 6;
export const GOBLIN_SHAMAN_DEF = 2;
export const GOBLIN_SHAMAN_SPD = 3;
export const GOBLIN_SHAMAN_GOLD = 10;
export const GOBLIN_SHAMAN_XP = 25;

// Floor 5: Goblin Chief
export const GOBLIN_CHIEF_HP = 120;
export const GOBLIN_CHIEF_ATK = 12;
export const GOBLIN_CHIEF_DEF = 4;
export const GOBLIN_CHIEF_SPD = 3;
export const GOBLIN_CHIEF_GOLD = 20;
export const GOBLIN_CHIEF_XP = 50;

// ── Auto-added by roadmap ──
export const DUNGEON_ENEMIES = [
    {
        name: 'Goblin',
        texture: 'enemy1',
        hp: GOBLIN_HP,
        attack: GOBLIN_ATK,
        defense: GOBLIN_DEF,
        speed: GOBLIN_SPD,
        goldReward: GOBLIN_GOLD,
        xpReward: GOBLIN_XP
    },
    {
        name: 'Goblin Warrior',
        texture: 'enemy2',
        hp: GOBLIN_WARRIOR_HP,
        attack: GOBLIN_WARRIOR_ATK,
        defense: GOBLIN_WARRIOR_DEF,
        speed: GOBLIN_WARRIOR_SPD,
        goldReward: GOBLIN_WARRIOR_GOLD,
        xpReward: GOBLIN_WARRIOR_XP
    },
    {
        name: 'Goblin Shaman',
        texture: 'enemy3',
        hp: GOBLIN_SHAMAN_HP,
        attack: GOBLIN_SHAMAN_ATK,
        defense: GOBLIN_SHAMAN_DEF,
        speed: GOBLIN_SHAMAN_SPD,
        goldReward: GOBLIN_SHAMAN_GOLD,
        xpReward: GOBLIN_SHAMAN_XP
    }
];

// ── Auto-added by roadmap ──
export const UPGRADE_BASE_ATK_COST = 50;

export const UPGRADE_ATK_COST_MULTIPLIER = 1.5;

export const UPGRADE_ATK_AMOUNT = 5;

export const UPGRADE_BASE_DEF_COST = 40;

export const UPGRADE_DEF_COST_MULTIPLIER = 1.4;

export const UPGRADE_DEF_AMOUNT = 3;

export const UPGRADE_BASE_HP_COST = 60;

export const UPGRADE_HP_COST_MULTIPLIER = 1.6;

export const UPGRADE_HP_AMOUNT = 20;
