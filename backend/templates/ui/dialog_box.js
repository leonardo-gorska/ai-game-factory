/**
 * GORVAX TEMPLATE — Dialog Box System
 *
 * Features:
 * - Typewriter text effect
 * - Character portraits and names
 * - Branching dialogue choices
 * - Dialog trees with callbacks
 * - Skip/fast-forward support
 */

class DialogNode {
    constructor(id, speaker, text, config = {}) {
        this.id = id;
        this.speaker = speaker;
        this.text = text;
        this.portrait = config.portrait || null;
        this.choices = config.choices || []; // [{ text, nextNodeId, condition?, onSelect? }]
        this.nextNodeId = config.nextNodeId || null;
        this.onEnter = config.onEnter || null;
        this.onExit = config.onExit || null;
        this.emotion = config.emotion || 'neutral';
    }
}

class DialogBox {
    constructor(canvas, config = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.width = canvas.width;
        this.height = canvas.height;

        // Dialog box dimensions
        this.boxHeight = config.boxHeight || 150;
        this.boxPadding = config.boxPadding || 20;
        this.boxY = this.height - this.boxHeight - 20;

        // Typewriter
        this.typeSpeed = config.typeSpeed || 30; // ms per character
        this.currentText = '';
        this.displayText = '';
        this.charIndex = 0;
        this.lastCharTime = 0;
        this.isTyping = false;

        // State
        this.currentNode = null;
        this.dialogTree = new Map();
        this.isActive = false;
        this.selectedChoice = 0;
        this.listeners = [];
    }

    registerTree(nodes) {
        nodes.forEach(node => {
            this.dialogTree.set(node.id, node);
        });
    }

    start(startNodeId) {
        const node = this.dialogTree.get(startNodeId);
        if (!node) return;
        this.isActive = true;
        this._showNode(node);
    }

    _showNode(node) {
        this.currentNode = node;
        this.currentText = node.text;
        this.displayText = '';
        this.charIndex = 0;
        this.isTyping = true;
        this.selectedChoice = 0;
        this.lastCharTime = Date.now();

        if (node.onEnter) node.onEnter(node);
        this._notify('node_enter', { nodeId: node.id, speaker: node.speaker });
    }

    update(dt) {
        if (!this.isActive || !this.isTyping) return;

        const now = Date.now();
        while (now - this.lastCharTime >= this.typeSpeed && this.charIndex < this.currentText.length) {
            this.displayText += this.currentText[this.charIndex];
            this.charIndex++;
            this.lastCharTime += this.typeSpeed;
        }

        if (this.charIndex >= this.currentText.length) {
            this.isTyping = false;
        }
    }

    render() {
        if (!this.isActive || !this.currentNode) return;
        const ctx = this.ctx;
        const node = this.currentNode;
        const bx = 20;
        const by = this.boxY;
        const bw = this.width - 40;
        const bh = this.boxHeight;

        // Box background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        ctx.strokeStyle = '#ecf0f1';
        ctx.lineWidth = 2;
        ctx.fillRect(bx, by, bw, bh);
        ctx.strokeRect(bx, by, bw, bh);

        // Speaker name
        ctx.fillStyle = '#f1c40f';
        ctx.font = 'bold 16px monospace';
        ctx.textAlign = 'left';
        ctx.fillText(node.speaker, bx + this.boxPadding, by + 24);

        // Dialog text (with word wrap)
        ctx.fillStyle = '#ecf0f1';
        ctx.font = '14px monospace';
        this._drawWrappedText(this.displayText, bx + this.boxPadding, by + 48, bw - this.boxPadding * 2, 20);

        // Choices (if typing is done and choices exist)
        if (!this.isTyping && node.choices.length > 0) {
            const choiceY = by + bh + 10;
            node.choices.forEach((choice, i) => {
                const isSelected = i === this.selectedChoice;
                ctx.fillStyle = isSelected ? '#f1c40f' : '#bdc3c7';
                ctx.font = `${isSelected ? 'bold ' : ''}14px monospace`;
                ctx.fillText(`${isSelected ? '▶ ' : '  '}${choice.text}`, bx + this.boxPadding, choiceY + i * 24);
            });
        }

        // Continue indicator
        if (!this.isTyping && node.choices.length === 0) {
            ctx.fillStyle = '#7f8c8d';
            ctx.font = '12px monospace';
            ctx.textAlign = 'right';
            ctx.fillText('▼ Continue', bx + bw - this.boxPadding, by + bh - 10);
        }
    }

    advance() {
        if (!this.isActive || !this.currentNode) return;

        // Fast-forward typewriter
        if (this.isTyping) {
            this.displayText = this.currentText;
            this.charIndex = this.currentText.length;
            this.isTyping = false;
            return;
        }

        const node = this.currentNode;
        if (node.onExit) node.onExit(node);

        // Handle choices
        if (node.choices.length > 0) {
            const choice = node.choices[this.selectedChoice];
            if (choice.onSelect) choice.onSelect(choice);
            this._notify('choice_selected', { choice, index: this.selectedChoice });
            if (choice.nextNodeId) {
                const next = this.dialogTree.get(choice.nextNodeId);
                if (next) { this._showNode(next); return; }
            }
        } else if (node.nextNodeId) {
            const next = this.dialogTree.get(node.nextNodeId);
            if (next) { this._showNode(next); return; }
        }

        // End dialog
        this.isActive = false;
        this.currentNode = null;
        this._notify('dialog_end', {});
    }

    selectChoice(direction) {
        if (!this.currentNode || this.isTyping) return;
        const len = this.currentNode.choices.length;
        if (len === 0) return;
        this.selectedChoice = (this.selectedChoice + direction + len) % len;
    }

    _drawWrappedText(text, x, y, maxWidth, lineHeight) {
        const words = text.split(' ');
        let line = '';
        let currentY = y;
        for (const word of words) {
            const testLine = line + word + ' ';
            if (this.ctx.measureText(testLine).width > maxWidth && line) {
                this.ctx.fillText(line.trim(), x, currentY);
                line = word + ' ';
                currentY += lineHeight;
            } else {
                line = testLine;
            }
        }
        if (line.trim()) this.ctx.fillText(line.trim(), x, currentY);
    }

    onChange(callback) {
        this.listeners.push(callback);
    }

    _notify(event, data) {
        this.listeners.forEach(cb => cb(event, data));
    }
}
