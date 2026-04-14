/**
 * GORVAX TEMPLATE — Finite State Machine
 *
 * Features:
 * - Named states with enter/update/exit hooks
 * - Transition conditions and guards
 * - State history for debugging
 * - Hierarchical state support (parent states)
 * - Event-driven transitions
 */

class State {
    constructor(name, config = {}) {
        this.name = name;
        this.onEnter = config.onEnter || (() => { });
        this.onUpdate = config.onUpdate || (() => { });
        this.onExit = config.onExit || (() => { });
        this.transitions = config.transitions || {};
        this.parent = config.parent || null;
    }
}

class StateMachine {
    constructor(config = {}) {
        this.states = new Map();
        this.currentState = null;
        this.previousState = null;
        this.history = [];
        this.maxHistory = config.maxHistory || 20;
        this.context = config.context || {};
        this.listeners = [];
    }

    addState(state) {
        this.states.set(state.name, state);
        return this;
    }

    setState(name) {
        const newState = this.states.get(name);
        if (!newState) {
            console.warn(`[FSM] State "${name}" not found`);
            return false;
        }

        if (this.currentState) {
            this.currentState.onExit(this.context);
            this.previousState = this.currentState;
            this.history.push({
                from: this.currentState.name,
                to: name,
                timestamp: Date.now(),
            });
            if (this.history.length > this.maxHistory) this.history.shift();
        }

        this.currentState = newState;
        this.currentState.onEnter(this.context);
        this._notify('state_change', { from: this.previousState?.name, to: name });
        return true;
    }

    update(dt) {
        if (!this.currentState) return;
        this.currentState.onUpdate(dt, this.context);
    }

    trigger(event, data = {}) {
        if (!this.currentState) return false;
        const transition = this.currentState.transitions[event];
        if (!transition) return false;

        // Guard check
        if (transition.guard && !transition.guard(this.context, data)) {
            return false;
        }

        // Execute transition action
        if (transition.action) {
            transition.action(this.context, data);
        }

        return this.setState(transition.target);
    }

    is(stateName) {
        return this.currentState?.name === stateName;
    }

    getHistory() {
        return [...this.history];
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}

// ── Game State Machine Factory ──
function createGameStateMachine() {
    const fsm = new StateMachine();

    fsm.addState(new State('loading', {
        onEnter: () => console.log('[Game] Loading...'),
        transitions: {
            loaded: { target: 'menu' },
        },
    }));

    fsm.addState(new State('menu', {
        onEnter: () => console.log('[Game] Main Menu'),
        transitions: {
            start_game: { target: 'playing' },
            quit: { target: 'quit' },
        },
    }));

    fsm.addState(new State('playing', {
        onEnter: () => console.log('[Game] Playing'),
        transitions: {
            pause: { target: 'paused' },
            game_over: { target: 'game_over' },
            win: { target: 'victory' },
        },
    }));

    fsm.addState(new State('paused', {
        onEnter: () => console.log('[Game] Paused'),
        transitions: {
            resume: { target: 'playing' },
            quit: { target: 'menu' },
        },
    }));

    fsm.addState(new State('game_over', {
        onEnter: () => console.log('[Game] Game Over'),
        transitions: {
            retry: { target: 'playing' },
            menu: { target: 'menu' },
        },
    }));

    fsm.addState(new State('victory', {
        onEnter: () => console.log('[Game] Victory!'),
        transitions: {
            continue: { target: 'menu' },
        },
    }));

    return fsm;
}
