# lean-server/app.py
import os
import json
import tempfile
import subprocess
import threading
import select
import uuid
import time
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


def _build_lean_env() -> dict | None:
    """
    Разово собираем окружение `lake env` (LEAN_PATH/LEAN_SRC_PATH/LAKE_ENV/ PATH с elan).
    Так избавляемся от вызова `lake env` на каждый запрос — Lean стартует быстрее.
    """
    cmd = ["lake", "env", "--", "/usr/bin/env"]
    p = subprocess.run(
        cmd,
        cwd=str(MATHLIB_ROOT),
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        # fallback: None => будем вызывать lake env на каждый запуск
        return None
    env = os.environ.copy()
    for line in p.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v
    return env


LEAN_ENV = _build_lean_env()


def _decode_severity(code: int | None) -> str | None:
    # LSP severity: 1 error, 2 warning, 3 info, 4 hint
    mapping = {1: "error", 2: "warning", 3: "information", 4: "hint"}
    return mapping.get(code or 0)


class LeanServer:
    """Держим один живой `lean --server`, чтобы Mathlib не грузить на каждый запрос."""

    def __init__(self):
        if LEAN_ENV is None:
            raise RuntimeError("LEAN_ENV not prepared; cannot start lean --server fast path")
        self.proc = subprocess.Popen(
            ["lean", "--server"],
            cwd=str(MATHLIB_ROOT),
            env=LEAN_ENV,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.lock = threading.Lock()
        self._msg_id = 1
        self._init_server()

    def _send(self, obj: dict):
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        assert self.proc.stdin is not None
        self.proc.stdin.write(header + data)
        self.proc.stdin.flush()

    def _read_message(self, timeout: float = 30.0) -> dict:
        assert self.proc.stdout is not None
        start = time.time()
        content_length = None
        # читаем заголовки
        while True:
            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                raise TimeoutError("Waiting for LSP header timed out")
            r, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not r:
                continue
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("lean --server stdout closed")
            line = line.strip()
            if not line:
                break  # пустая строка — конец заголовков
            if line.lower().startswith(b"content-length:"):
                try:
                    content_length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    pass
        if content_length is None:
            raise RuntimeError("No Content-Length in LSP response")
        # читаем тело
        body = self.proc.stdout.read(content_length)
        if body is None:
            raise RuntimeError("lean --server returned no body")
        return json.loads(body.decode("utf-8"))

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _init_server(self):
        root_uri = MATHLIB_ROOT.as_uri()
        init_msg = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "processId": None,
                "rootUri": root_uri,
                "workspaceFolders": [{"uri": root_uri, "name": "mathlib4"}],
                "capabilities": {
                    "textDocument": {
                        "publishDiagnostics": {"relatedInformation": True},
                        "diagnostic": {"dynamicRegistration": False},
                    }
                },
            },
        }
        self._send(init_msg)
        # ждем ответ на initialize
        while True:
            msg = self._read_message(timeout=60)
            if msg.get("id") == 0:
                break
        # отправляем initialized
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def check(self, file_path: Path) -> list[dict]:
        code = file_path.read_text(encoding="utf-8")
        uri = file_path.resolve().as_uri()
        with self.lock:
            # didOpen
            self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "lean",
                            "version": 1,
                            "text": code,
                        }
                    },
                }
            )
            # Явно шлем didChange, чтобы форсировать диагностику
            self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": uri, "version": 2},
                        "contentChanges": [{"text": code}],
                    },
                }
            )
            # Явный запрос diagnostics (LSP 3.17)
            diag_id = self._next_id()
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": diag_id,
                    "method": "textDocument/diagnostic",
                    "params": {
                        "textDocument": {"uri": uri},
                        "identifier": "lean-checker",
                    },
                }
            )
            diagnostics: list[dict] = []
            start = time.time()
            while True:
                msg = self._read_message(timeout=60)
                # отвечаем на запросы сервера, чтобы не блокировать диагностику
                if msg.get("method") == "workspace/configuration" and "id" in msg:
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": []})
                    continue
                if msg.get("method") == "client/registerCapability" and "id" in msg:
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
                    continue
                if msg.get("id") == diag_id:
                    res = msg.get("result") or {}
                    diagnostics = res.get("items", [])
                    break
                if (
                    msg.get("method") == "textDocument/publishDiagnostics"
                    and msg.get("params", {}).get("uri") == uri
                ):
                    diagnostics = msg["params"].get("diagnostics", [])
                    break
                if time.time() - start > 60:
                    raise TimeoutError("No diagnostics from lean --server")
            # закрываем документ, чтобы не захламлять сервер
            self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didClose",
                    "params": {"textDocument": {"uri": uri}},
                }
            )
        # нормализация в наш формат
        messages: list[dict] = []
        for d in diagnostics:
            rng = d.get("range", {}) or {}
            start_pos = rng.get("start", {}) or {}
            end_pos = rng.get("end", {}) or {}
            messages.append(
                {
                    "severity": _decode_severity(d.get("severity")),
                    "file": uri,
                    "line": start_pos.get("line"),
                    "column": start_pos.get("character"),
                    "endLine": end_pos.get("line"),
                    "endColumn": end_pos.get("character"),
                    "caption": None,
                    "message": d.get("message"),
                    "kind": "lsp",
                    "keepFullRange": None,
                    "raw": d,
                }
            )
        return messages


USE_LEAN_SERVER = os.environ.get("LEAN_SERVER", "0") == "1"
SERVER: LeanServer | None = None
if USE_LEAN_SERVER and LEAN_ENV is not None:
    try:
        SERVER = LeanServer()
    except Exception:
        SERVER = None


def run_lean(file_path: Path) -> dict:
    # Запускаем Lean с заранее собранным env, чтобы не звать `lake env` на каждый запрос.
    # Если сборка окружения не удалась, откатываемся к старому пути через `lake env`.
    if SERVER is not None:
        messages = SERVER.check(file_path)
        # stdout/stderr пустые — работаем через LSP
        return {
            "ok": all(m.get("severity") != "error" for m in messages),
            "returncode": 0 if not any(m.get("severity") == "error" for m in messages) else 1,
            "stdout": "",
            "stderr": "",
            "messages": messages,
            "cmd": ["lean", "--server", "(reused)"],
        }

    if LEAN_ENV is None:
        cmd = ["lake", "env", "lean", "--json", str(file_path)]
        run_env = None
    else:
        cmd = ["lean", "--json", str(file_path)]
        run_env = LEAN_ENV

    p = subprocess.run(
        cmd,
        cwd=str(MATHLIB_ROOT),
        capture_output=True,
        text=True,
        env=run_env,
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

    # Делаем временный файл прямо внутри проекта mathlib, чтобы LSP видел его как workspace file
    with tempfile.TemporaryDirectory(dir=MATHLIB_ROOT) as td:
        fp = Path(td) / "Main.lean"
        fp.write_text(code, encoding="utf-8")
        return run_lean(fp)
