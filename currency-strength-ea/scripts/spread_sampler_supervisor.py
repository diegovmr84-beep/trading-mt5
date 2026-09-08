#!/usr/bin/env python3
"""Supervisor externo do spread_sampler.

Motivo (observado rodando): o terminal MT5 às vezes fica num estado em que
o spread_sampler não consegue mais amostrar — ou fica vivo sem gravar nada,
ou nem inicializa (sai com 0xC0000142). Um watchdog in-process não resolve
de forma confiável. Um processo separado que mata e reinicia é robusto:
TerminateProcess no Windows mata qualquer processo, pendurado ou não.

O que faz: sobe o spread_sampler, e enquanto ele estiver vivo E gravando
amostra a cada poucos minutos, deixa rodar. Se morrer ou ficar mudo, mata e
sobe de novo — mas com BACKOFF EXPONENCIAL nas falhas seguidas, para não
transformar um hiccup transitório do MT5 num festival de 80 reinícios (já
aconteceu). Depois de N falhas seguidas, loga ALERTA — aí é problema real
no terminal/MT5 que precisa de olho humano.

Uso:
    python -m scripts.spread_sampler_supervisor
    (roda indefinidamente; Ctrl+C encerra o supervisor e o filho)
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CHECK_INTERVAL_SECONDS = 60
GRACE_AFTER_START_SECONDS = 150      # tempo pro filho conectar e gravar a 1ª amostra
STALE_LIMIT_SECONDS = 240            # ~8 ciclos de 30s sem amostra nova => reinicia
HEALTHY_RUN_SECONDS = 1800           # rodou > 30 min => zera o contador de falhas
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 1800
ALERT_AFTER_CONSECUTIVE = 5


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} [supervisor] {msg}", flush=True)


def latest_sample_epoch() -> int | None:
    try:
        conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=10)
        try:
            row = conn.execute("SELECT MAX(ts_utc) FROM spread_samples").fetchone()
        finally:
            conn.close()
        return row[0] if row and row[0] is not None else None
    except sqlite3.Error as exc:
        log(f"aviso: falha ao ler banco ({exc})")
        return None


def spawn() -> subprocess.Popen:
    env = dict(os.environ)
    env.setdefault("MT5_SYMBOL_SUFFIX", "m")
    repo = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "scripts.spread_sampler"],
        cwd=repo,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    log(f"spread_sampler iniciado (pid {proc.pid})")
    return proc


def kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.kill()  # Windows: TerminateProcess — forte, mata processo pendurado
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        log(f"pid {proc.pid} não morreu com kill(), tentando taskkill /F /T")
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


def watch(proc: subprocess.Popen, spawn_mono: float) -> str:
    """Bloqueia até o sampler precisar ser reiniciado; devolve o motivo."""
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        if proc.poll() is not None:
            return f"subprocesso saiu (exit {proc.returncode})"
        if time.monotonic() - spawn_mono <= GRACE_AFTER_START_SECONDS:
            continue
        latest = latest_sample_epoch()
        if latest is None:
            return "nenhuma amostra no banco"
        age = time.time() - latest
        if age > STALE_LIMIT_SECONDS:
            return f"sem amostra nova há {age:.0f}s (limite {STALE_LIMIT_SECONDS}s)"


def main() -> None:
    log("supervisor iniciado")
    consecutive_failures = 0

    try:
        while True:
            proc = spawn()
            spawn_mono = time.monotonic()
            reason = watch(proc, spawn_mono)
            ran_for = time.monotonic() - spawn_mono
            kill(proc)

            if ran_for >= HEALTHY_RUN_SECONDS:
                consecutive_failures = 0  # o que veio antes foi um bom trecho, não conta
            consecutive_failures += 1

            backoff = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (consecutive_failures - 1))
            level = "ALERTA" if consecutive_failures >= ALERT_AFTER_CONSECUTIVE else "reiniciando"
            log(
                f"{level}: {reason} | rodou {ran_for:.0f}s | {consecutive_failures}ª falha seguida "
                f"| espera {backoff}s antes de subir de novo"
            )
            if consecutive_failures >= ALERT_AFTER_CONSECUTIVE:
                log(
                    "ALERTA: spread_sampler não sustenta a coleta. Verifique o terminal MT5 "
                    "(aberto? logado na Exness-MT5Trial11? conectado?). O supervisor continua "
                    f"tentando a cada {BACKOFF_CAP_SECONDS // 60} min."
                )
            time.sleep(backoff)
    except KeyboardInterrupt:
        log("Ctrl+C — encerrando supervisor")
        try:
            kill(proc)  # type: ignore[name-defined]
        except NameError:
            pass


if __name__ == "__main__":
    main()
