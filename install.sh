#!/usr/bin/env bash
# One-line installer/runner for Lean 4.24 + Mathlib checker
set -euo pipefail

# Настраиваемые переменные (можно переопределить через env):
#   REPO_URL  — адрес git-репозитория
#   TARGET_DIR — куда клонировать проект
#   BRANCH    — ветка/тег
REPO_URL="${REPO_URL:-https://github.com/andreykhalov/lean-checker.git}"
TARGET_DIR="${TARGET_DIR:-$HOME/lean-checker}"
BRANCH="${BRANCH:-main}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[-] Требуется команда: $1" >&2
    exit 1
  }
}

need_cmd git
need_cmd docker

if ! docker info >/dev/null 2>&1; then
  echo "[-] Docker daemon не запущен или недоступен" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[-] Нужен Docker Compose V2 (docker compose). Установите/обновите Docker." >&2
  exit 1
fi

echo "[*] Клонируем или обновляем репозиторий $REPO_URL в $TARGET_DIR (ветка $BRANCH)"
if [ ! -d "$TARGET_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
else
  git -C "$TARGET_DIR" fetch --all --prune
  git -C "$TARGET_DIR" checkout "$BRANCH"
  git -C "$TARGET_DIR" pull --ff-only origin "$BRANCH"
fi

cd "$TARGET_DIR"

echo "[*] Стартуем контейнер (docker compose up --build -d)"
docker compose up --build -d

echo "[+] Готово. Проверка: curl -s http://localhost:8888/health"

