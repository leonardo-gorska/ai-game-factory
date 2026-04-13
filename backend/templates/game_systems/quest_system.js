/**
 * GORVAX TEMPLATE — Quest System
 *
 * Features:
 * - Quest types: main, side, daily, repeatable
 * - Multi-objective quests
 * - Quest chains (prerequisites)
 * - Reward distribution (XP, gold, items)
 * - Quest tracking and journal
 */

const QuestStatus = {
    LOCKED: 'locked',
    AVAILABLE: 'available',
    ACTIVE: 'active',
    COMPLETED: 'completed',
    TURNED_IN: 'turned_in',
};

class QuestObjective {
    constructor(id, description, type, target, requiredCount = 1) {
        this.id = id;
        this.description = description;
        this.type = type;  // 'kill', 'collect', 'reach', 'talk', 'interact'
        this.target = target;
        this.requiredCount = requiredCount;
        this.currentCount = 0;
    }

    get isComplete() {
        return this.currentCount >= this.requiredCount;
    }

    progress(targetId, amount = 1) {
        if (targetId === this.target && !this.isComplete) {
            this.currentCount = Math.min(this.requiredCount, this.currentCount + amount);
            return true;
        }
        return false;
    }
}

class Quest {
    constructor(id, name, description, config = {}) {
        this.id = id;
        this.name = name;
        this.description = description;
        this.type = config.type || 'side'; // 'main', 'side', 'daily', 'repeatable'
        this.status = QuestStatus.LOCKED;
        this.objectives = (config.objectives || []).map(
            o => new QuestObjective(o.id, o.description, o.type, o.target, o.requiredCount)
        );
        this.rewards = config.rewards || { xp: 0, gold: 0, items: [] };
        this.prerequisites = config.prerequisites || [];
        this.level = config.level || 1;
        this.timeLimit = config.timeLimit || 0; // 0 = no limit, in ms
        this.startTime = 0;
    }

    get isComplete() {
        return this.objectives.every(o => o.isComplete);
    }

    get progress() {
        const total = this.objectives.reduce((s, o) => s + o.requiredCount, 0);
        const current = this.objectives.reduce((s, o) => s + o.currentCount, 0);
        return total > 0 ? current / total : 1;
    }

    start() {
        this.status = QuestStatus.ACTIVE;
        this.startTime = Date.now();
    }

    updateObjective(type, targetId, amount = 1) {
        if (this.status !== QuestStatus.ACTIVE) return [];

        const updated = [];
        this.objectives.forEach(obj => {
            if (obj.type === type && obj.progress(targetId, amount)) {
                updated.push(obj);
            }
        });

        if (this.isComplete) {
            this.status = QuestStatus.COMPLETED;
        }

        return updated;
    }

    checkTimeLimit() {
        if (this.timeLimit <= 0 || this.status !== QuestStatus.ACTIVE) return true;
        return Date.now() - this.startTime < this.timeLimit;
    }
}

class QuestManager {
    constructor() {
        this.quests = new Map();
        this.activeQuests = [];
        this.completedQuests = [];
        this.listeners = [];
    }

    registerQuest(quest) {
        this.quests.set(quest.id, quest);
    }

    checkAvailability(completedQuestIds, playerLevel) {
        const nowAvailable = [];
        this.quests.forEach(quest => {
            if (quest.status !== QuestStatus.LOCKED) return;
            if (playerLevel < quest.level) return;
            const prereqsMet = quest.prerequisites.every(p => completedQuestIds.includes(p));
            if (prereqsMet) {
                quest.status = QuestStatus.AVAILABLE;
                nowAvailable.push(quest);
            }
        });
        return nowAvailable;
    }

    acceptQuest(questId) {
        const quest = this.quests.get(questId);
        if (!quest || quest.status !== QuestStatus.AVAILABLE) return null;

        quest.start();
        this.activeQuests.push(quest);
        this._notify('quest_accepted', { quest });
        return quest;
    }

    onEvent(type, targetId, amount = 1) {
        const results = [];
        this.activeQuests.forEach(quest => {
            const updated = quest.updateObjective(type, targetId, amount);
            if (updated.length > 0) {
                results.push({ quest, updated });
                this._notify('quest_progress', { quest, objectives: updated });
            }
            if (quest.isComplete) {
                this._notify('quest_completed', { quest });
            }
        });
        return results;
    }

    turnIn(questId) {
        const quest = this.quests.get(questId);
        if (!quest || quest.status !== QuestStatus.COMPLETED) return null;

        quest.status = QuestStatus.TURNED_IN;
        this.activeQuests = this.activeQuests.filter(q => q.id !== questId);
        this.completedQuests.push(quest);
        this._notify('quest_turned_in', { quest, rewards: quest.rewards });
        return quest.rewards;
    }

    getActiveQuests() {
        return this.activeQuests.filter(q => q.status === QuestStatus.ACTIVE);
    }

    getAvailableQuests() {
        return [...this.quests.values()].filter(q => q.status === QuestStatus.AVAILABLE);
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}
