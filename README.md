# 🏭 AI Game Factory

Pipeline autônomo de desenvolvimento de jogos controlado por 9 agentes de IA especializados que criam, testam e evoluem jogos de navegador sem intervenção humana.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat&logo=nextdotjs&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-010101?style=flat&logo=socketdotio&logoColor=white)

## Como funciona

Você aperta **Start** no dashboard e 9 agentes de IA trabalham em loop:

```
Researcher → Designer → Developer → Build → Tester
→ Critic → Performance → Simulator → Economy → Memory
```

A cada iteração, o jogo melhora. O sistema calcula um **Quality Score** (0-100) e usa guardiões automáticos para evitar regressões e estagnação.

## Os 9 Agentes

| Agente | Função |
|--------|--------|
| 🔬 Researcher | Pesquisa tendências de game design |
| 🎨 Designer | Cria e atualiza o Game Design Document |
| 💻 Developer | Escreve o código do jogo |
| 🧪 Tester | Analisa bugs e dá nota de diversão |
| 🧐 Critic | Avalia criticamente e sugere melhorias |
| ⚡ Performance | Analisa métricas técnicas e otimização |
| 🎮 Simulator | Simula jogadores e coleta dados de engajamento |
| 💰 Economy Guardian | Verifica se a economia do jogo está balanceada |
| 🧠 Memory Curator | Salva lições aprendidas para não repetir erros |

## Sistemas inteligentes

- **Quality Engine** — Score composto com 6 dimensões (diversão, estabilidade, performance, balanceamento, novidade, retenção)
- **Cost Guard** — Controle de gastos com LLMs
- **Stagnation Guard** — Detecta quando o jogo para de evoluir e força inovação
- **Novelty Engine** — Garante que cada iteração traga algo novo
- **Exploit Detector** — Identifica vulnerabilidades no game design

## Stack

- **Backend:** Python, FastAPI, SQLite, WebSocket
- **Dashboard:** Next.js 15, Chakra UI v3
- **LLMs:** OpenAI, Anthropic, Google, OpenRouter (roteamento inteligente)
- **Infra:** Docker, testes com pytest

## Como rodar

```bash
# Backend
python -m venv venv && venv\Scripts\activate
pip install -r backend/requirements.txt

# Dashboard
cd dashboard && npm install

# Iniciar tudo
python start.py
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000
- Game: http://localhost:5173

## Licença

MIT
