/**
 * GORVAX TEMPLATE — Event Bus (Pub/Sub)
 *
 * Features:
 * - Subscribe/unsubscribe with named events
 * - Priority-based listener ordering
 * - One-time listeners (once)
 * - Wildcard subscriptions
 * - Event history for debugging
 * - Async event emission
 */

class EventBus {
    constructor(config = {}) {
        this.listeners = new Map();
        this.history = [];
        this.maxHistory = config.maxHistory || 100;
        this.debug = config.debug || false;
    }

    on(event, callback, priority = 0) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        const entry = { callback, priority, once: false, id: this._uid() };
        this.listeners.get(event).push(entry);
        this.listeners.get(event).sort((a, b) => b.priority - a.priority);
        return entry.id;
    }

    once(event, callback, priority = 0) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        const entry = { callback, priority, once: true, id: this._uid() };
        this.listeners.get(event).push(entry);
        this.listeners.get(event).sort((a, b) => b.priority - a.priority);
        return entry.id;
    }

    off(event, callbackOrId) {
        const list = this.listeners.get(event);
        if (!list) return;

        if (typeof callbackOrId === 'string') {
            this.listeners.set(event, list.filter(e => e.id !== callbackOrId));
        } else {
            this.listeners.set(event, list.filter(e => e.callback !== callbackOrId));
        }
    }

    emit(event, data = {}) {
        if (this.debug) {
            console.log(`[EventBus] ${event}`, data);
        }

        this.history.push({ event, data, timestamp: Date.now() });
        if (this.history.length > this.maxHistory) this.history.shift();

        const toRemove = [];

        // Exact match
        const list = this.listeners.get(event) || [];
        list.forEach(entry => {
            entry.callback(data, event);
            if (entry.once) toRemove.push({ event, id: entry.id });
        });

        // Wildcard listeners
        const wildcardList = this.listeners.get('*') || [];
        wildcardList.forEach(entry => {
            entry.callback(data, event);
            if (entry.once) toRemove.push({ event: '*', id: entry.id });
        });

        // Clean up one-time listeners
        toRemove.forEach(({ event: e, id }) => this.off(e, id));
    }

    async emitAsync(event, data = {}) {
        const list = this.listeners.get(event) || [];
        for (const entry of list) {
            await entry.callback(data, event);
            if (entry.once) this.off(event, entry.id);
        }
    }

    clear(event) {
        if (event) {
            this.listeners.delete(event);
        } else {
            this.listeners.clear();
        }
    }

    getHistory(event = null) {
        if (event) return this.history.filter(h => h.event === event);
        return [...this.history];
    }

    listenerCount(event) {
        return (this.listeners.get(event) || []).length;
    }

    _uid() {
        return Math.random().toString(36).substr(2, 9);
    }
}

// Singleton for global events
const globalEventBus = new EventBus();
