/**
 * GORVAX TEMPLATE — Shop System
 *
 * Features:
 * - Dynamic pricing (supply/demand simulation)
 * - Buy/sell with markup
 * - Stock limits and restocking
 * - Discount events
 * - Purchase history tracking
 */

class ShopItem {
    constructor(itemId, name, basePrice, stock = -1, category = 'general') {
        this.itemId = itemId;
        this.name = name;
        this.basePrice = basePrice;
        this.currentPrice = basePrice;
        this.stock = stock; // -1 = infinite
        this.maxStock = stock;
        this.category = category;
        this.purchaseCount = 0;
        this.sellMarkup = 0.5; // player sells at 50% of current price
    }

    get sellPrice() {
        return Math.floor(this.currentPrice * this.sellMarkup);
    }
}

class Shop {
    constructor(name, inventory = []) {
        this.name = name;
        this.inventory = inventory;
        this.discountRate = 0;
        this.purchaseHistory = [];
        this.restockInterval = 300000; // 5 min in ms
        this.lastRestock = Date.now();
    }

    buy(itemId, quantity, playerGold) {
        const item = this.inventory.find(i => i.itemId === itemId);
        if (!item) return { success: false, reason: 'item_not_found' };
        if (item.stock !== -1 && item.stock < quantity) return { success: false, reason: 'out_of_stock' };

        const price = this._calculatePrice(item, quantity);
        if (playerGold < price) return { success: false, reason: 'insufficient_gold' };

        if (item.stock !== -1) item.stock -= quantity;
        item.purchaseCount += quantity;

        // Dynamic pricing: price goes up with demand
        item.currentPrice = Math.floor(item.basePrice * (1 + item.purchaseCount * 0.02));

        this.purchaseHistory.push({
            itemId, quantity, price,
            timestamp: Date.now(), type: 'buy',
        });

        return { success: true, cost: price, item };
    }

    sell(itemId, name, quantity, basePrice) {
        let item = this.inventory.find(i => i.itemId === itemId);
        if (!item) {
            item = new ShopItem(itemId, name, basePrice);
            this.inventory.push(item);
        }

        const revenue = item.sellPrice * quantity;
        if (item.stock !== -1) item.stock += quantity;

        // Dynamic pricing: more supply, lower price
        item.currentPrice = Math.max(
            Math.floor(item.basePrice * 0.5),
            item.currentPrice - Math.floor(item.basePrice * 0.01 * quantity)
        );

        this.purchaseHistory.push({
            itemId, quantity, price: revenue,
            timestamp: Date.now(), type: 'sell',
        });

        return { success: true, revenue, item };
    }

    _calculatePrice(item, quantity) {
        const unitPrice = Math.floor(item.currentPrice * (1 - this.discountRate));
        return unitPrice * quantity;
    }

    setDiscount(rate, durationMs = 60000) {
        this.discountRate = Math.min(0.5, rate);
        setTimeout(() => { this.discountRate = 0; }, durationMs);
    }

    restock() {
        this.inventory.forEach(item => {
            if (item.maxStock !== -1) {
                item.stock = item.maxStock;
                item.currentPrice = item.basePrice; // reset pricing
            }
        });
        this.lastRestock = Date.now();
    }

    checkRestock() {
        if (Date.now() - this.lastRestock >= this.restockInterval) {
            this.restock();
            return true;
        }
        return false;
    }

    getByCategory(category) {
        return this.inventory.filter(i => i.category === category);
    }

    toJSON() {
        return {
            name: this.name,
            inventory: this.inventory,
            discountRate: this.discountRate,
            lastRestock: this.lastRestock,
        };
    }
}
