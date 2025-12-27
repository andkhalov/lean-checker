# lean-server/app.py
import os
import json
import tempfile
import subprocess
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel

MATHLIB_ROOT = Path(os.environ.get("MATHLIB_ROOT", "/opt/mathlib4")).resolve()

app = FastAPI(title="Lean 4.24 + Mathlib checker")

class CheckRequest(BaseModel):
    code: str
    # опционально: имя модуля для импорта вместо Mathlib
    # (по умолчанию — import Mathlib)
    import_line: str | None = "import Mathlib"

def _parse_messages(stdout: str) -> list[dict]:
    """Lean --json печатает по сообщению в строке; собираем читаемую структуру."""
    msgs: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        pos = raw.get("pos") or {}
        end = raw.get("endPos") or {}
        msgs.append(
            {
                "severity": raw.get("severity"),
                "file": raw.get("fileName"),
                "line": pos.get("line"),
                "column": pos.get("column"),
                "endLine": end.get("line"),
                "endColumn": end.get("column"),
                "caption": raw.get("caption"),  # название/контекст (если есть)
                "message": raw.get("data"),
                "kind": raw.get("kind"),
                "keepFullRange": raw.get("keepFullRange"),
                "raw": raw,
            }
        )
    return msgs


def run_lean(file_path: Path) -> dict:
    # Запускаем именно внутри mathlib-проекта; --json для структурированных сообщений
    cmd = ["lake", "env", "lean", "--json", str(file_path)]
    p = subprocess.run(
        cmd,
        cwd=str(MATHLIB_ROOT),
        capture_output=True,
        text=True,
    )
    messages = _parse_messages(p.stdout)
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "messages": messages,
        "cmd": cmd,
    }

@app.get("/health")
def health():
    # простой smoke-test
    fp = Path("/srv/health.lean")
    res = run_lean(fp)
    return {"service": "ok", "lean_ok": res["ok"], "stderr": res["stderr"][-800:]}

@app.post("/check")
def check(req: CheckRequest):
    # создаём временный файл, добавляем import (если пользователь не добавил сам)
    code = req.code.strip()
    if req.import_line and not code.startswith("import "):
        code = f"{req.import_line}\n\n{code}\n"

    with tempfile.TemporaryDirectory() as td:
        fp = Path(td) / "Main.lean"
        fp.write_text(code, encoding="utf-8")
        return run_lean(fp)
