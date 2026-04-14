# Contributing to GORVAX GAME FACTORY

Thank you for your interest in contributing! This guide covers the development workflow, project conventions, and how to extend the system.

## 🛠 Local Development Setup

### Prerequisites

- Python 3.11+ with `venv`
- Node.js 18+ with `npm`
- At least one LLM API key configured in `.env`

### Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd ai-game-factory

# Backend
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt

# Dashboard
cd dashboard && npm install
```

### Running Locally

```bash
# All-in-one
python start.py

# Or separately:
python -m backend.main       # API on :8000
cd dashboard && npm run dev   # UI on :3000
```

## 📁 Project Structure

| Directory | Purpose |
|-----------|---------|
| `backend/agents/` | 9 specialized AI agents (designer, developer, tester, etc.) |
| `backend/api/` | FastAPI server (`server.py`) + WebSocket (`ws.py`) |
| `backend/core/` | Guards, engines, trackers (cost, stagnation, novelty, etc.) |
| `backend/game/` | Game builder, playtest simulator, evaluator |
| `backend/llm/` | LLM router, prompt engine, prompt versioner |
| `backend/orchestrator/` | Pipeline loop, state management, step functions |
| `backend/storage/` | SQLite database layer |
| `dashboard/src/lib/` | API client, DashboardContext, WebSocket client, i18n |
| `dashboard/src/app/` | Next.js pages (overview, evolution, simulation, etc.) |
| `tests/` | Backend test suite (pytest) |

## ➕ Adding a New Agent

1. Create `backend/agents/your_agent.py`
2. Extend the base agent class with `name`, `system_prompt`, and `run()` method
3. Create the prompt template in `backend/llm/prompts/your_agent.md`
4. Register the agent in `backend/orchestrator/pipeline.py` (`__init__`)
5. Add a step call in `_run_iteration()` at the appropriate stage

## 🎮 Adding a New Game Genre

1. Add genre mechanics in `backend/llm/prompt_engine.py` → `GENRE_MECHANICS` dict
2. Create a `SimulationStrategy` subclass in `backend/game/simulator.py`:
   - Implement `get_default_params()`, `init_state()`, and `run_tick()`
3. Register it in `_GENRE_STRATEGIES` dict
4. Add the genre to `SUPPORTED_GENRES` in `backend/config.py`
5. Optionally add engine features in `ENGINE_FEATURES`

## 🔧 Adding a New Engine

1. Add engine config in `backend/llm/prompt_engine.py` → `ENGINE_FEATURES` dict
2. Add to `SUPPORTED_ENGINES` in `backend/config.py`
3. Update builder logic in `backend/game/builder.py` if needed

## 🏗 Conventions

### Python (Backend)

- **Linter**: `ruff` — run `ruff check backend/` before committing
- **Formatter**: `ruff format backend/`
- **Type hints**: Use throughout, prefer `dict[str, Any]` over bare `dict`
- **Logging**: Use `logger = logging.getLogger(__name__)`, not `print()`
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes

### TypeScript (Dashboard)

- **Framework**: Next.js 15 (App Router) + Chakra UI v3
- **Linter**: ESLint (via `npm run lint`)
- **State**: React Context (`DashboardContext`) for global state
- **i18n**: Use `useTranslation()` hook — add strings to `en.json` and `pt-br.json`

### Commit Messages

Use conventional commits:

```
feat: add puzzle simulation strategy
fix: cursor pagination returning wrong count
docs: update API endpoints in README
refactor: extract _run_single to strategy pattern
```

## 🧪 Testing

```bash
# Run all backend tests
python -m pytest tests/ -v --tb=short

# Run specific test file
python -m pytest tests/test_database.py -v

# Dashboard build check (catches type errors)
cd dashboard && npm run build
```

### Writing Tests

- Place tests in `tests/` directory
- Name files `test_*.py`
- Use `pytest` fixtures for shared setup
- Mock LLM calls — never call real APIs in tests

## 📋 PR Guidelines

1. **Branch** from `main` with descriptive name: `feat/puzzle-strategy`, `fix/ws-heartbeat`
2. **Test** your changes locally (`pytest` + `npm run build`)
3. **Lint** before pushing (`ruff check` + `npm run lint`)
4. **Describe** what changed and why in the PR description
5. **Keep PRs focused** — one feature/fix per PR
