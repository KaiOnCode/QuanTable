# Contributing to QuanTable

Thank you for your interest in contributing to QuanTable. This guide covers development setup, coding standards, and the pull request process.

## Development Setup

### Prerequisites

- Python 3.12
- Node.js 22+
- uv (Python package manager)
- A DeepSeek API key or any OpenAI-compatible key

### Backend

```bash
git clone https://github.com/KaiOnCode/QuanTable.git
cd QuanTable
cp properties.env.example properties.env
# Edit properties.env with your API credentials

uv sync
PYTHONPATH=. uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Python tests
uv run pytest

# Lint
uv run ruff check .
uv run ruff format --check .
```

## Code Standards

### Python

- Target Python 3.12. Use modern syntax (type hints, `match`, `|` union types).
- All code comments and docstrings must be in English.
- Use `snake_case` for variables, functions, and module names. Use `PascalCase` for classes.
- Use Pydantic for all structured output models.
- Format with `ruff format`, lint with `ruff check`.
- Never fabricate financial data. Return empty results or clear error messages on failure.

### TypeScript / Frontend

- Follow the existing ESLint configuration.
- Use functional components with hooks.
- Use TanStack Query for server state, Zustand for client state.
- Field names in JSON must match between frontend and backend (snake_case).

### Architecture Rules

The codebase is divided into three tracks with strict boundaries:

```
agent/        = ACTIVE   (main development -- ReAct agent terminal)
quick_ask/    = LEGACY   (frozen -- do not modify or extend)
skills/       = ACTIVE   (shared between both tracks)
```

**Hard rules:**

- Never import from `quick_ask/` into active code (`agent/`, `server/routes/agent.py`).
- Never add new agents to `quick_ask/`. Use skills or tools instead.
- Never modify `quick_ask/`. It is frozen.
- New features go in `agent/loop.py`, `agent/tools/`, or `skills/`.

### Commit Messages

Use the format: `<type>: <description>`

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

Examples:
```
feat: add MACD crossover detection to technical indicators tool
fix: handle empty DataFrame in YFinance provider fallback
docs: update architecture diagram for dual-track design
```

## Pull Request Process

1. Fork the repository and create a feature branch from `main`.
2. Make your changes following the code standards above.
3. Run the full test suite: `uv run pytest` and `cd frontend && npm run lint`.
4. Write a clear PR description explaining what changed and why.
5. Reference any related issues (e.g., `Closes #12`).
6. Request a review. PRs require at least one approval before merge.

### PR Checklist

- [ ] Code follows the project coding standards
- [ ] Comments and docstrings are in English
- [ ] No hardcoded API keys, file paths, or magic numbers
- [ ] Tests pass (`uv run pytest`)
- [ ] Lint passes (`uv run ruff check .`)
- [ ] Documentation updated if user-facing behavior changed
- [ ] No modifications to `quick_ask/` (legacy, frozen)

## Reporting Issues

Use the [GitHub Issues](https://github.com/KaiOnCode/QuanTable/issues) page. When reporting a bug:

1. Describe the expected behavior and actual behavior.
2. Include steps to reproduce.
3. Provide your environment (OS, Python version, Node version).
4. Include relevant logs or error messages.

## Security

If you discover a security vulnerability, please see [SECURITY.md](SECURITY.md) for responsible disclosure instructions. Do not open a public issue for security vulnerabilities. Do not open a public issue for security vulnerabilities.

## License

By contributing to QuanTable, you agree that your contributions will be licensed under the MIT License.
