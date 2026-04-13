/**
 * GORVAX TEMPLATE — Inventory System
 * 
 * Features:
 * - Add/remove items with stack support
 * - Weight and capacity limits
 * - Item categories and filtering
 * - Equip/unequip slots
 * - Event notifications on changes
 */

class InventoryItem {
    constructor(id, name, category, stackable = true, maxStack = 99, weight = 1) {
        this.id = id;
        this.name = name;
        this.category = category; // 'weapon', 'armor', 'consumable', 'material', 'quest'
        this.stackable = stackable;
        this.maxStack = maxStack;
        this.weight = weight;
        this.quantity = 1;
        this.metadata = {};
    }

    clone() {
        const item = new InventoryItem(this.id, this.name, this.category, this.stackable, this.maxStack, this.weight);
        item.quantity = this.quantity;
        item.metadata = { ...this.metadata };
        return item;
    }
}

class Inventory {
    constructor(maxSlots = 20, maxWeight = 100) {
        this.slots = [];
        this.maxSlots = maxSlots;
        this.maxWeight = maxWeight;
        this.equipped = {}; // slot -> item
        this.listeners = [];
    }

    get currentWeight() {
        return this.slots.reduce((w, item) => w + item.weight * item.quantity, 0);
    }

    get freeSlots() {
        return this.maxSlots - this.slots.length;
    }

    addItem(item, quantity = 1) {
        const totalWeight = this.currentWeight + item.weight * quantity;
        if (totalWeight > this.maxWeight) {
            this._notify('inventory_full_weight', { item, quantity });
            return false;
        }

        if (item.stackable) {
            const existing = this.slots.find(s => s.id === item.id && s.quantity < s.maxStack);
            if (existing) {
                const canAdd = Math.min(quantity, existing.maxStack - existing.quantity);
                existing.quantity += canAdd;
                quantity -= canAdd;
                if (quantity <= 0) {
                    this._notify('item_added', { item: existing });
                    return true;
                }
            }
        }

        if (this.freeSlots <= 0) {
            this._notify('inventory_full_slots', { item, quantity });
            return false;
        }

        const newItem = item.clone();
        newItem.quantity = quantity;
        this.slots.push(newItem);
        this._notify('item_added', { item: newItem });
        return true;
    }

    removeItem(itemId, quantity = 1) {
        const idx = this.slots.findIndex(s => s.id === itemId);
        if (idx === -1) return false;

        const slot = this.slots[idx];
        slot.quantity -= quantity;
        if (slot.quantity <= 0) {
            this.slots.splice(idx, 1);
        }
        this._notify('item_removed', { itemId, quantity });
        return true;
    }

    getByCategory(category) {
        return this.slots.filter(s => s.category === category);
    }

    equip(itemId, equipSlot) {
        const item = this.slots.find(s => s.id === itemId);
        if (!item) return false;

        if (this.equipped[equipSlot]) {
            this.addItem(this.equipped[equipSlot]);
        }
        this.equipped[equipSlot] = item;
        this.removeItem(itemId, 1);
        this._notify('item_equipped', { item, slot: equipSlot });
        return true;
    }

    unequip(equipSlot) {
        const item = this.equipped[equipSlot];
        if (!item) return false;

        if (!this.addItem(item)) return false;
        delete this.equipped[equipSlot];
        this._notify('item_unequipped', { item, slot: equipSlot });
        return true;
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }

    toJSON() {
        return {
            slots: this.slots,
            equipped: this.equipped,
            maxSlots: this.maxSlots,
            maxWeight: this.maxWeight,
        };
    }

    static fromJSON(data) {
        const inv = new Inventory(data.maxSlots, data.maxWeight);
        inv.slots = data.slots.map(s => Object.assign(new InventoryItem(s.id, s.name, s.category), s));
        inv.equipped = data.equipped || {};
        return inv;
    }
}
