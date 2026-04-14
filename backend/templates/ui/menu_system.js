/**
 * GORVAX TEMPLATE — Menu System
 *
 * Features:
 * - Main menu, pause menu, settings
 * - Keyboard/mouse navigation
 * - Animated transitions
 * - Settings persistence (localStorage)
 * - Screen stack (push/pop)
 */

class MenuItem {
    constructor(label, action, config = {}) {
        this.label = label;
        this.action = action; // function or submenu name
        this.enabled = config.enabled !== false;
        this.type = config.type || 'button'; // 'button', 'toggle', 'slider'
        this.value = config.value ?? null;
        this.min = config.min ?? 0;
        this.max = config.max ?? 100;
    }
}

class MenuScreen {
    constructor(name, title, items = []) {
        this.name = name;
        this.title = title;
        this.items = items;
        this.selectedIndex = 0;
    }

    selectNext() {
        do {
            this.selectedIndex = (this.selectedIndex + 1) % this.items.length;
        } while (!this.items[this.selectedIndex].enabled && this.items.length > 1);
    }

    selectPrev() {
        do {
            this.selectedIndex = (this.selectedIndex - 1 + this.items.length) % this.items.length;
        } while (!this.items[this.selectedIndex].enabled && this.items.length > 1);
    }

    getSelected() {
        return this.items[this.selectedIndex];
    }
}

class MenuSystem {
    constructor(canvas, config = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.width = canvas.width;
        this.height = canvas.height;

        this.screens = new Map();
        this.screenStack = [];
        this.isActive = false;
        this.transition = { active: false, alpha: 0, direction: 'in' };
        this.transitionSpeed = config.transitionSpeed || 4;
        this.listeners = [];

        // Settings persistence
        this.settings = this._loadSettings();
    }

    registerScreen(screen) {
        this.screens.set(screen.name, screen);
    }

    open(screenName) {
        const screen = this.screens.get(screenName);
        if (!screen) return;
        this.screenStack.push(screen);
        this.isActive = true;
        this.transition = { active: true, alpha: 0, direction: 'in' };
        this._notify('menu_open', { screen: screenName });
    }

    close() {
        if (this.screenStack.length > 0) {
            const closed = this.screenStack.pop();
            this._notify('menu_close', { screen: closed.name });
        }
        if (this.screenStack.length === 0) {
            this.isActive = false;
        }
    }

    back() {
        if (this.screenStack.length > 1) {
            this.close();
        } else {
            this.close();
        }
    }

    get currentScreen() {
        return this.screenStack[this.screenStack.length - 1] || null;
    }

    update(dt) {
        if (this.transition.active) {
            if (this.transition.direction === 'in') {
                this.transition.alpha = Math.min(1, this.transition.alpha + this.transitionSpeed * dt);
                if (this.transition.alpha >= 1) this.transition.active = false;
            } else {
                this.transition.alpha = Math.max(0, this.transition.alpha - this.transitionSpeed * dt);
                if (this.transition.alpha <= 0) this.transition.active = false;
            }
        }
    }

    render() {
        if (!this.isActive || !this.currentScreen) return;
        const ctx = this.ctx;
        const screen = this.currentScreen;

        ctx.save();
        ctx.globalAlpha = this.transition.active ? this.transition.alpha : 1;

        // Overlay
        ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        ctx.fillRect(0, 0, this.width, this.height);

        // Title
        ctx.fillStyle = '#f1c40f';
        ctx.font = 'bold 32px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(screen.title, this.width / 2, 80);

        // Menu items
        const startY = 160;
        const itemHeight = 45;
        screen.items.forEach((item, i) => {
            const y = startY + i * itemHeight;
            const isSelected = i === screen.selectedIndex;

            // Highlight
            if (isSelected) {
                ctx.fillStyle = 'rgba(241, 196, 15, 0.15)';
                ctx.fillRect(this.width / 2 - 150, y - 20, 300, 36);
            }

            ctx.fillStyle = !item.enabled ? '#555' : isSelected ? '#f1c40f' : '#ecf0f1';
            ctx.font = `${isSelected ? 'bold ' : ''}18px monospace`;
            ctx.textAlign = 'center';

            let label = item.label;
            if (item.type === 'toggle') label += `: ${item.value ? 'ON' : 'OFF'}`;
            if (item.type === 'slider') label += `: ${item.value}`;

            ctx.fillText(label, this.width / 2, y);
        });

        ctx.restore();
    }

    handleInput(action) {
        if (!this.isActive || !this.currentScreen) return;
        const screen = this.currentScreen;
        const item = screen.getSelected();

        switch (action) {
            case 'up': screen.selectPrev(); break;
            case 'down': screen.selectNext(); break;
            case 'confirm':
                if (!item.enabled) break;
                if (item.type === 'toggle') {
                    item.value = !item.value;
                    this._saveSetting(item.label, item.value);
                } else if (typeof item.action === 'string') {
                    this.open(item.action);
                } else if (typeof item.action === 'function') {
                    item.action();
                }
                this._notify('menu_select', { item: item.label });
                break;
            case 'left':
                if (item.type === 'slider') {
                    item.value = Math.max(item.min, item.value - 5);
                    this._saveSetting(item.label, item.value);
                }
                break;
            case 'right':
                if (item.type === 'slider') {
                    item.value = Math.min(item.max, item.value + 5);
                    this._saveSetting(item.label, item.value);
                }
                break;
            case 'back': this.back(); break;
        }
    }

    _saveSetting(key, value) {
        this.settings[key] = value;
        try { localStorage.setItem('game_settings', JSON.stringify(this.settings)); } catch { }
    }

    _loadSettings() {
        try {
            return JSON.parse(localStorage.getItem('game_settings') || '{}');
        } catch { return {}; }
    }

    getSetting(key, defaultValue) {
        return this.settings[key] ?? defaultValue;
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}
