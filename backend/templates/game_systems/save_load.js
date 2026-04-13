/**
 * GORVAX TEMPLATE — Save/Load System
 *
 * Features:
 * - Auto-save with configurable interval
 * - Multiple save slots
 * - Save data versioning and migration
 * - Compression via JSON serialization
 * - Cloud save stub (localStorage fallback)
 */

const SAVE_VERSION = 1;

class SaveManager {
    constructor(maxSlots = 3, autoSaveInterval = 60000) {
        this.maxSlots = maxSlots;
        this.autoSaveInterval = autoSaveInterval;
        this.autoSaveTimer = null;
        this.listeners = [];
        this.storageKey = 'game_saves';
    }

    save(slot, gameState) {
        if (slot < 0 || slot >= this.maxSlots) return false;

        const saveData = {
            version: SAVE_VERSION,
            slot,
            timestamp: Date.now(),
            playTime: gameState.playTime || 0,
            data: this._serialize(gameState),
            checksum: this._checksum(gameState),
        };

        const saves = this._getAllSaves();
        saves[slot] = saveData;
        this._writeSaves(saves);
        this._notify('saved', { slot, timestamp: saveData.timestamp });
        return true;
    }

    load(slot) {
        const saves = this._getAllSaves();
        const saveData = saves[slot];
        if (!saveData) return null;

        // Version migration
        if (saveData.version < SAVE_VERSION) {
            this._migrate(saveData);
        }

        // Integrity check
        const data = this._deserialize(saveData.data);
        if (this._checksum(data) !== saveData.checksum) {
            this._notify('corruption_detected', { slot });
            // Still return data, let game decide what to do
        }

        this._notify('loaded', { slot, timestamp: saveData.timestamp });
        return data;
    }

    delete(slot) {
        const saves = this._getAllSaves();
        if (!saves[slot]) return false;
        delete saves[slot];
        this._writeSaves(saves);
        this._notify('deleted', { slot });
        return true;
    }

    getSaveInfo() {
        const saves = this._getAllSaves();
        const info = [];
        for (let i = 0; i < this.maxSlots; i++) {
            if (saves[i]) {
                info.push({
                    slot: i,
                    timestamp: saves[i].timestamp,
                    playTime: saves[i].playTime,
                    version: saves[i].version,
                    exists: true,
                });
            } else {
                info.push({ slot: i, exists: false });
            }
        }
        return info;
    }

    startAutoSave(slot, getGameState) {
        this.stopAutoSave();
        this.autoSaveTimer = setInterval(() => {
            const state = getGameState();
            this.save(slot, state);
            this._notify('auto_saved', { slot });
        }, this.autoSaveInterval);
    }

    stopAutoSave() {
        if (this.autoSaveTimer) {
            clearInterval(this.autoSaveTimer);
            this.autoSaveTimer = null;
        }
    }

    _serialize(gameState) {
        return JSON.stringify(gameState);
    }

    _deserialize(data) {
        return JSON.parse(data);
    }

    _checksum(data) {
        const str = typeof data === 'string' ? data : JSON.stringify(data);
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit int
        }
        return hash.toString(16);
    }

    _migrate(saveData) {
        // Add migration steps as versions increase
        // Example: if (saveData.version === 0) { ... saveData.version = 1; }
        saveData.version = SAVE_VERSION;
    }

    _getAllSaves() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            return raw ? JSON.parse(raw) : {};
        } catch {
            return {};
        }
    }

    _writeSaves(saves) {
        localStorage.setItem(this.storageKey, JSON.stringify(saves));
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}
