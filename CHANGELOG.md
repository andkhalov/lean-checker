# Changelog

# lean-checker v1.0.0 — Lean 4 + Mathlib Verification Service

First public release of **lean-checker** — a containerized FastAPI service that verifies Lean 4 source code inside a pinned Mathlib environment and returns structured JSON diagnostics with error coordinates.
## What it is

A Dockerized verification endpoint built on `leanprover/lean4:v4.24.0` with `mathlib4 v4.24.0`. The `lake env` and Mathlib `olean` cache are built once on container start and reused for all subsequent checks. Each request runs `lean --json` against the supplied source and returns parsed diagnostics.
Used as the proof-verification backend for SciLib-GRC21 experiments (50,752 Lean-verified proof attempts on MiniF2F).
## API

- `GET /health` — smoke-test against an internal Lean file.
- `POST /check` — body `{"code": "<Lean source>", "import_line": "import Mathlib"}`. Returns `ok`, `returncode`, `stdout`, `stderr`, and a structured `messages` array with `{severity, file, line, column, endLine, endColumn, message, kind, raw}` per diagnostic.
## Quick start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/andkhalov/lean-checker/main/install.sh)
```

Or manually:

```bash
git clone https://github.com/andkhalov/lean-checker.git
cd lean-checker
docker compose up --build -d
curl -s http://localhost:8888/health
```

## License

MIT.
## Citation

```bibtex
@misc{lean_checker_2026,
 author = {Khalov, Andrey P. and Ataeva, Olga M. and Tuchkova, Natalia P.},
 title = {{lean-checker}: A Lean 4 + Mathlib Verification Service},
 year = {2026},
 publisher = {Zenodo},
 version = {v1.0.0},
 doi = {(DOI minted automatically by Zenodo on release)},
 url = {https://github.com/andkhalov/lean-checker}
}
```

## Authors

- **Andrey P. Khalov** —
 Moscow Institute of Physics and Technology (MIPT), Dolgoprudny, Russia;
 Federal Research Center "Computer Science and Control" of the Russian Academy of Sciences, Moscow, Russia ·
 ORCID: [0009-0005-4584-8245](https://orcid.org/0009-0005-4584-8245) ·
 `khalov.a@phystech.edu`
- **Olga M. Ataeva** — FRC CSC RAS · ORCID: [0000-0003-0367-5575](https://orcid.org/0000-0003-0367-5575) · `oataeva@frccsc.ru`
- **Natalia P. Tuchkova** — FRC CSC RAS · ORCID: [0000-0001-5357-9640](https://orcid.org/0000-0001-5357-9640) · `ntuchkova@frccsc.ru`
