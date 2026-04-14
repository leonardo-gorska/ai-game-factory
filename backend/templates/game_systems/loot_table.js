/**
 * GORVAX TEMPLATE — Loot Table System
 *
 * Features:
 * - Weighted drop rates with rarity tiers
 * - Guaranteed drops and bonus rolls
 * - Level-scaled loot
 * - Pity system (bad luck protection)
 * - Drop history for analytics
 */

const RARITY = {
    common: { weight: 60, color: '#b0b0b0', multiplier: 1.0 },
    uncommon: { weight: 25, color: '#1eff00', multiplier: 1.3 },
    rare: { weight: 10, color: '#0070ff', multiplier: 1.7 },
    epic: { weight: 4, color: '#a335ee', multiplier: 2.5 },
    legendary: { weight: 1, color: '#ff8000', multiplier: 4.0 },
};

class LootEntry {
    constructor(itemId, name, rarity = 'common', minLevel = 1, weight = null) {
        this.itemId = itemId;
        this.name = name;
        this.rarity = rarity;
        this.minLevel = minLevel;
        this.weight = weight ?? RARITY[rarity].weight;
    }
}

class LootTable {
    constructor(entries = [], guaranteedDrops = []) {
        this.entries = entries;
        this.guaranteedDrops = guaranteedDrops; // always drop these
        this.pityCounters = {}; // rarity -> rolls since last drop
        this.pityThresholds = { epic: 50, legendary: 100 };
        this.history = [];
    }

    roll(playerLevel = 1, bonusRolls = 0, luckMultiplier = 1.0) {
        const drops = [...this.guaranteedDrops];
        const eligible = this.entries.filter(e => playerLevel >= e.minLevel);

        if (eligible.length === 0) return drops;

        const rollCount = 1 + bonusRolls;
        for (let i = 0; i < rollCount; i++) {
            const drop = this._weightedRoll(eligible, luckMultiplier);
            if (drop) {
                drops.push(drop);
                this._updatePity(drop.rarity, true);
            } else {
                this._updatePity(null, false);
            }
        }

        this.history.push({
            level: playerLevel,
            drops: drops.map(d => d.itemId),
            timestamp: Date.now(),
        });

        return drops;
    }

    _weightedRoll(entries, luckMultiplier = 1.0) {
        const adjusted = entries.map(entry => {
            let w = entry.weight;
            // Pity system: boost rare+ drop rates
            const pity = this.pityCounters[entry.rarity] || 0;
            const threshold = this.pityThresholds[entry.rarity];
            if (threshold && pity >= threshold * 0.5) {
                w *= 1 + (pity / threshold) * 2;
            }
            // Luck multiplier boosts rare drops
            if (RARITY[entry.rarity].weight <= 10) {
                w *= luckMultiplier;
            }
            return { entry, weight: w };
        });

        const totalWeight = adjusted.reduce((sum, a) => sum + a.weight, 0);
        let roll = Math.random() * totalWeight;

        for (const { entry, weight } of adjusted) {
            roll -= weight;
            if (roll <= 0) return entry;
        }

        return adjusted[adjusted.length - 1].entry;
    }

    _updatePity(droppedRarity, gotDrop) {
        for (const rarity of ['epic', 'legendary']) {
            if (droppedRarity === rarity) {
                this.pityCounters[rarity] = 0;
            } else {
                this.pityCounters[rarity] = (this.pityCounters[rarity] || 0) + 1;
            }
        }
    }

    addEntry(entry) {
        this.entries.push(entry);
    }

    getDropRates() {
        const totalWeight = this.entries.reduce((s, e) => s + e.weight, 0);
        return this.entries.map(e => ({
            item: e.name,
            rarity: e.rarity,
            rate: ((e.weight / totalWeight) * 100).toFixed(2) + '%',
        }));
    }
}
