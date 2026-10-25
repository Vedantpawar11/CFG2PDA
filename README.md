# CFG2PDA — Grammar Lab

A small, beginner-friendly Theory of Computation project that parses and validates a context-free grammar (CFG), converts it to an equivalent pushdown automaton (PDA), visualizes the transition graph, and simulates input strings with a stack trace.

## Features

- Grammar editor with a cursor-aware special-symbol palette (`ε`, `→`, `|`, `λ`).
- Epsilon aliases: `ε`, `eps`, `epsilon`, `λ`, and `lambda`.
- Grammar validation with errors and warnings, plus a compact grammar summary.
- Eight built-in grammars: `aⁿbⁿ`, balanced parentheses, strings ending in `b`, palindromes, positive `aⁿbⁿ`, only `a` strings, even numbers of `a`s, and one-or-more `a`s followed by one-or-more `b`s.
- CFG-to-PDA conversion implemented locally in Python; no external conversion API.
- Interactive graph with draggable states, zoom, pan, minimap, and controls.
- Generated transition table and step-by-step conversion explanation.
- Nondeterministic BFS simulation with branch-specific traces, visited configurations, and stack-depth/configuration/step limits.
- Accepted, rejected, invalid-input, and limit-reached outcomes.
- Shopping-order API validator with separate JSON syntax and CFG-to-PDA structural checks.
- Compact API Request Validator workspace with syntax and CFG-to-PDA checks from the request input box.
- Step trace, auto-run, current stack view, JSON/CSV export, and transition highlighting synchronized with the selected trace step.
- Editing any grammar field clears stale validation/PDA/simulation output so old results cannot be mistaken for the current grammar.
- Local system-font fallbacks; no remote font download is required.
- Pytest coverage for parser, validation, converter, and simulator.

## Tech stack

- Backend: Python 3.11+, FastAPI, Pydantic, Uvicorn
- Frontend: React, Vite, JavaScript, CSS, `@xyflow/react`, Lucide icons
- Tests: pytest
- No database, authentication, or AI/external conversion API is needed.

## Folder structure

```text
cfg2pda/
├── backend/
│   ├── main.py                 # API, parser, validator, converter, simulator
│   ├── requirements.txt
│   └── tests/
│       └── test_main.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── App.css
├── .gitignore
└── README.md
```

The implementation intentionally keeps the number of files small for a short student repository while separating the frontend from the backend. The functions in `backend/main.py` are kept independent and named by responsibility so they can be moved into separate modules later if the team needs that.

## Setup and run

Use Python 3.11–3.13 for the smoothest compatibility with common scientific and web packages. Open two terminals from the `cfg2pda` folder.

### 1. Backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

- Windows PowerShell: `\.venv\Scripts\Activate.ps1`
- Windows Command Prompt: `.venv\Scripts\activate.bat`
- macOS/Linux: `source .venv/bin/activate`

Then install and start the API:

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Backend health check: `http://127.0.0.1:8000/health`  
Interactive API docs: `http://127.0.0.1:8000/docs`

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The frontend expects the API at `http://127.0.0.1:8000` by default. To change it, create `frontend/.env` with:

```env
VITE_API_URL=http://127.0.0.1:8000
```

## Example grammar

Variables: `S`  
Terminals: `a b`  
Start symbol: `S`

```text
S → aSb | ε
```

Accepted strings: empty string (`ε`), `ab`, `aabb`, `aaabbb`  
Rejected strings: `a`, `abb`, `aab`, `abab`

For an empty string test, leave the input field blank or enter `ε`.

## Built-in examples

Use the Example dropdown to load any of the eight grammars. After editing a grammar, click **Validate grammar** and then **Generate PDA** again before simulating. The sample buttons are convenience inputs; the backend simulation result is the source of truth.

## Algorithm overview

A CFG is `G = (V, Σ, P, S)`. The generated PDA uses states `q0`, `q1`, and `qf`; stack-bottom marker `Z0`; and acceptance by final state. The stack is represented **top to bottom** (index zero is the top).

1. Initialize with `ε, Z0 → SZ0`.
2. For each production `A → α`, add `ε, A → α`; for epsilon productions, push no symbols.
3. For each terminal `a`, add `a, a → ε` to consume the matching input symbol and pop the terminal.
4. Add `ε, Z0 → ε` to enter `qf` when the stack-bottom marker is reached. Acceptance requires that the entire input has been consumed.
5. The simulator explores possible configurations with breadth-first search (BFS), recording `(state, input position, stack)` and skipping visited configurations. Configurable safety limits prevent runaway exploration.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/examples` | Built-in grammars |
| POST | `/api/grammar/parse` | Parse production text into normalized CFG JSON |
| POST | `/api/grammar/validate` | Validate CFG structure and symbols |
| POST | `/api/grammar/summary` | Return counts and normalized productions |
| POST | `/api/pda/convert` | Generate PDA and conversion steps |
| POST | `/api/pda/simulate` | Simulate an input string against PDA JSON |
| POST | `/api/api-validator` | Validate JSON syntax and shopping-order/selected-CFG structure |
| POST | `/api/boundary-tests` | Execute the automated boundary and edge-case suite |

FastAPI's `/docs` page includes request schemas and interactive endpoint testing.

## Tests

From `backend/` with the virtual environment activated:

```bash
pytest -q
```

The API validator is the primary frontend workflow: paste a request into the input box and choose
JSON syntax validation or CFG-to-PDA structural validation. The validator reports JSON syntax
independently from structural recognition: valid JSON can still be rejected by the configured grammar.
The default shopping-order validator
requires an `order` object containing an `items` array; each item must contain only a string
`product` and a positive integer `quantity`. CFG structural validation does not establish
authorization, security, or business correctness.

## Team of four

1. **Grammar and input:** parser, validation, epsilon aliases, examples, and symbol palette.
2. **Converter:** PDA data contract, conversion algorithm, transitions, and conversion explanation.
3. **Simulator:** BFS, stack operations, trace, visited configurations, and safety limits.
4. **Frontend and integration:** React interface, graph, table, controls, API integration, and demo.

## Known limitations

- Initial grammar syntax supports single-character variables (uppercase letters) and single-character terminals. Write symbol lists separated by spaces; the production RHS is tokenized character-by-character.
- Multi-character terminals/variables and quoted terminal syntax are not supported.
- The graph groups edges that share a source and destination to keep the visualization readable; all transitions remain individually available in the table and PDA JSON.
- BFS is bounded by the configured limits. A `LIMIT REACHED` result means exploration stopped at a safety threshold; it is not a rejection.
- The UI uses system-font fallbacks to remain usable offline.
- The default API structure grammar encodes the validated shopping-order shape into CFG terminals
  before running the existing PDA recognizer; this keeps JSON parsing and CFG recognition separate.

## Future improvements

- Split backend services into separate modules as the team grows.
- Add exportable trace CSV and richer transition highlighting.
- Add nullable/unreachable-variable analysis and optional grammar simplification.
- Add frontend component tests and deployment instructions.
