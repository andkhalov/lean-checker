## Lean checker (Lean 4.24 + Mathlib)

API-сервис на FastAPI, который проверяет Lean-код внутри mathlib4 (v4.24.0). Возвращает `ok: true/false`; для ошибок — структурированный JSON с координатами.

### Требования
- Docker + Docker Compose v2 (`docker compose version`)
- Git

### Быстрый старт (1 строка)
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/andreykhalov/lean-checker/main/install.sh)
```
Параметры (env): `REPO_URL`, `TARGET_DIR`, `BRANCH`. По умолчанию клонирует в `~/lean-checker` и запускает `docker compose up --build -d`.

### Ручной запуск
```bash
git clone https://github.com/andreykhalov/lean-checker.git
cd lean-checker
docker compose up --build -d
```
Проверка: `curl -s http://localhost:8888/health`

### API
- `GET /health` — smoke-test Lean (внутренний файл `/srv/health.lean`).
- `POST /check`
  - body: `{"code": "<Lean source as string>", "import_line": "import Mathlib"}` (`import_line` опционально; если не указан и код не начинается с `import`, сервер добавит `import Mathlib`).
  - ответ:  
    - `ok: bool` — успешная проверка  
    - `returncode` — код Lean  
    - `stdout` / `stderr` — исходный вывод Lean  
    - `messages` — массив структурированных сообщений Lean `--json`, каждое:
      ```json
      {
        "severity": "error",
        "file": "/tmp/.../Main.lean",
        "line": 19,
        "column": 4,
        "endLine": 19,
        "endColumn": 32,
        "caption": "",
        "message": "Function expected at\n  zipLeft'\n...",
        "kind": "[anonymous]",
        "keepFullRange": false,
        "raw": { "...": "оригинал строки из Lean --json" }
      }
      ```

### Примеры запросов
```bash
# Успешный пример
python3 - <<'PY' | curl -s -X POST http://localhost:8888/check \
  -H 'Content-Type: application/json' -d @-
import json
print(json.dumps({"code": open("test_ok.lean").read()}))
PY

# Ошибка с координатами
python3 - <<'PY' | curl -s -X POST http://localhost:8888/check \
  -H 'Content-Type: application/json' -d @-
import json
print(json.dumps({"code": open("test_bug.lean").read()}))
PY
```

### Стек
- Lean `leanprover/lean4:v4.24.0`
- mathlib4 `v4.24.0` (с кешированием olean через volume)
- FastAPI + Uvicorn
- Dockerfile собирает mathlib и запускает API на `:8000` (проброшен на `localhost:8888` через docker compose).

### Полезное
- Переменная `MATHLIB_ROOT` может переопределять путь к mathlib (по умолчанию `/opt/mathlib4` внутри контейнера).
- Повторные сборки быстро стартуют за счёт volume-кэшей `elan` и `.lake`.

