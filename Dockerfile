# lean-server/Dockerfile
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG LEAN_TOOLCHAIN=leanprover/lean4:v4.24.0
# Важно: tag/commit mathlib лучше фиксировать.
# На практике у mathlib есть "mathlib v4.24.0" линия (как в playground), но теги на GitHub могут называться иначе.
# Поэтому ниже — параметризуем checkout.
ARG MATHLIB_REF=v4.24.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates build-essential python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# elan + lean toolchain
RUN curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y
ENV PATH="/root/.elan/bin:${PATH}"

RUN elan toolchain install ${LEAN_TOOLCHAIN} && \
    elan default ${LEAN_TOOLCHAIN}

# --- mathlib project pinned ---
WORKDIR /opt
RUN git clone https://github.com/leanprover-community/mathlib4.git
WORKDIR /opt/mathlib4

# Попытка checkout на ref (tag/commit/branch)
RUN git checkout ${MATHLIB_REF} || (echo "WARN: could not checkout ${MATHLIB_REF}, staying on default branch" && true)

# Ставим кэшированные olean (очень важно по скорости)
# Команда cache get — нормальная практика в mathlib. :contentReference[oaicite:3]{index=3}
RUN lake exe cache get || true
RUN lake build Mathlib

# --- API app ---
WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /srv/requirements.txt

COPY app.py /srv/app.py
COPY health.lean /srv/health.lean

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host=0.0.0.0", "--port=8000"]
