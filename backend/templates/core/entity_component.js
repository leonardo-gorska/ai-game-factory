/**
 * GORVAX TEMPLATE — Entity-Component System (ECS)
 *
 * Features:
 * - Entity creation with unique IDs
 * - Component-based data storage
 * - System loop for logic processing
 * - Entity queries by component combination
 * - Entity pooling and recycling
 */

let _nextEntityId = 0;

class Entity {
    constructor() {
        this.id = _nextEntityId++;
        this.components = new Map();
        this.active = true;
        this.tags = new Set();
    }

    addComponent(name, data) {
        this.components.set(name, data);
        return this;
    }

    removeComponent(name) {
        this.components.delete(name);
        return this;
    }

    getComponent(name) {
        return this.components.get(name);
    }

    hasComponent(name) {
        return this.components.has(name);
    }

    hasAllComponents(...names) {
        return names.every(n => this.components.has(n));
    }

    addTag(tag) {
        this.tags.add(tag);
        return this;
    }

    hasTag(tag) {
        return this.tags.has(tag);
    }

    destroy() {
        this.active = false;
    }
}

class System {
    constructor(name, requiredComponents, updateFn) {
        this.name = name;
        this.requiredComponents = requiredComponents;
        this.updateFn = updateFn;
        this.enabled = true;
        this.priority = 0;
    }
}

class World {
    constructor() {
        this.entities = new Map();
        this.systems = [];
        this.entityPool = [];
        this.listeners = [];
    }

    createEntity() {
        let entity;
        if (this.entityPool.length > 0) {
            entity = this.entityPool.pop();
            entity.active = true;
            entity.components.clear();
            entity.tags.clear();
        } else {
            entity = new Entity();
        }
        this.entities.set(entity.id, entity);
        return entity;
    }

    removeEntity(entityId) {
        const entity = this.entities.get(entityId);
        if (entity) {
            entity.destroy();
            this.entities.delete(entityId);
            this.entityPool.push(entity); // recycle
            this._notify('entity_removed', { entityId });
        }
    }

    getEntity(entityId) {
        return this.entities.get(entityId);
    }

    addSystem(system) {
        this.systems.push(system);
        this.systems.sort((a, b) => a.priority - b.priority);
        return this;
    }

    query(...componentNames) {
        const results = [];
        this.entities.forEach(entity => {
            if (entity.active && entity.hasAllComponents(...componentNames)) {
                results.push(entity);
            }
        });
        return results;
    }

    queryByTag(tag) {
        const results = [];
        this.entities.forEach(entity => {
            if (entity.active && entity.hasTag(tag)) {
                results.push(entity);
            }
        });
        return results;
    }

    update(dt) {
        for (const system of this.systems) {
            if (!system.enabled) continue;
            const matching = this.query(...system.requiredComponents);
            for (const entity of matching) {
                system.updateFn(entity, dt, this);
            }
        }

        // Clean up destroyed entities
        const destroyed = [];
        this.entities.forEach((entity, id) => {
            if (!entity.active) destroyed.push(id);
        });
        destroyed.forEach(id => {
            const entity = this.entities.get(id);
            this.entities.delete(id);
            this.entityPool.push(entity);
        });
    }

    getStats() {
        return {
            entities: this.entities.size,
            systems: this.systems.length,
            pooled: this.entityPool.length,
        };
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}

// ── Common Components ──
const Components = {
    position: (x = 0, y = 0) => ({ x, y }),
    velocity: (vx = 0, vy = 0) => ({ vx, vy }),
    sprite: (src, width = 32, height = 32) => ({ src, width, height, frame: 0 }),
    health: (max = 100) => ({ current: max, max }),
    collider: (width = 32, height = 32, solid = true) => ({ width, height, solid }),
    input: () => ({ keys: {}, mouse: { x: 0, y: 0, down: false } }),
};

// ── Common Systems ──
const Systems = {
    movement: new System('movement', ['position', 'velocity'], (entity, dt) => {
        const pos = entity.getComponent('position');
        const vel = entity.getComponent('velocity');
        pos.x += vel.vx * dt;
        pos.y += vel.vy * dt;
    }),

    healthCheck: new System('healthCheck', ['health'], (entity, dt, world) => {
        const health = entity.getComponent('health');
        if (health.current <= 0) {
            entity.destroy();
        }
    }),
};
