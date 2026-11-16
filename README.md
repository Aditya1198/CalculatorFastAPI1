# FastAPI Calculator Application (API + Docker + Web UI)

A complete FastAPI calculator application featuring a safe AST-based expression parser (no `eval()`), strict Pydantic validation, an in-memory 20-item history log, a responsive single-page HTML/JS calculator UI served at `GET /`, a comprehensive `pytest` suite, and a lightweight production `Dockerfile` (< 200 MB).

---

## Project Structure

```text
calculator-app/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, safe AST parser, Pydantic schemas, endpoints
│   └── static/
│       └── index.html       # Single-page Calculator UI served at GET /
├── tests/
│   ├── __init__.py
│   └── test_main.py         # Pytest suite covering all endpoints & edge cases
├── .dockerignore
├── Dockerfile               # Multi-layer cached python:3.11-slim with non-root user
├── docker-compose.yml       # Compose file exposing port 8000 with healthcheck
├── requirements.txt
└── README.md
```

---

## Part 1: FastAPI Calculator API & Tests

### 1. Install Dependencies & Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- **Calculator Web UI**: [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger UI (`/docs`)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check (`/health`)**: [http://localhost:8000/health](http://localhost:8000/health)

### 2. API Endpoints Summary

| Method | Endpoint | Request Body | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | — | Serves the interactive single-page HTML/JS Calculator UI |
| `GET` | `/health` | — | Returns `{"status": "healthy"}` |
| `POST` | `/add` | `{"a": 10, "b": 5}` | Returns `a + b` (`15.0`) |
| `POST` | `/subtract` | `{"a": 10, "b": 5}` | Returns `a - b` (`5.0`) |
| `POST` | `/multiply` | `{"a": 10, "b": 5}` | Returns `a * b` (`50.0`) |
| `POST` | `/divide` | `{"a": 10, "b": 5}` | Returns `a / b` (`2.0`); returns HTTP `400` on division by zero |
| `POST` | `/power` | `{"a": 2, "b": 8}` | Returns `a ** b` (`256.0`) |
| `POST` | `/calculate` | `{"expression": "2 + 3 * 4"}` | Evaluates expression via a safe `ast` parser (returns `14.0`) |
| `GET` | `/history` | — | Returns the last 20 calculations stored in memory |
| `DELETE` | `/history` | — | Clears the in-memory calculation history |

### 3. Run the Test Suite

```bash
pytest -v
# Or run directly with Python:
python3 tests/test_main.py
```

---

## Part 2: Docker Image & Container Execution

### 1. Build the Image

The `Dockerfile` uses `python:3.11-slim`, creates a non-root user (`appuser`), and installs `requirements.txt` before copying `app/` so the dependency layer caches cleanly. Final image size is ~145 MB (well below the 200 MB target).

```bash
docker build -t calculator-api .
docker images calculator-api
```

### 2. Run the Container

```bash
docker run -d --name calculator-api -p 8000:8000 calculator-api
```

### 3. Test the Running Container

```bash
# Check /docs and /health
curl -i http://localhost:8000/health
curl -I http://localhost:8000/docs

# Call POST /add
curl -X POST http://localhost:8000/add \
  -H "Content-Type: application/json" \
  -d '{"a": 15, "b": 27}'

# Call POST /calculate
curl -X POST http://localhost:8000/calculate \
  -H "Content-Type: application/json" \
  -d '{"expression": "2 + 3 * 4"}'
```

### 4. Optional: Docker Compose & Docker Hub Push

```bash
# Start via Docker Compose
docker compose up -d --build

# Tag and push to Docker Hub
docker tag calculator-api:latest <your-dockerhub-username>/calculator-api:latest
docker push <your-dockerhub-username>/calculator-api:latest
```

---

## Part 3: Calculator Web UI

Open [http://localhost:8000/](http://localhost:8000/) in your browser while the container or `uvicorn` server is running:

- **Interactive Keypad & Expression Display**: Click digits, parentheses, and operator buttons (`+`, `-`, `×`, `÷`, `x^y`) or type directly and press `=` / `Enter` to evaluate via `POST /calculate`.
- **Direct Endpoint Caller**: Test `POST /add`, `/subtract`, `/multiply`, `/divide`, and `/power` with two input numbers (`a` and `b`).
- **Live History Panel**: Automatically fetches the last 20 calculations from `GET /history`; click any history entry to load it back into the display.
- **Friendly Error Banner**: Displays clear user-friendly error alerts whenever the API returns HTTP `400` (such as division by zero or invalid syntax) or `422` (non-numeric inputs).
