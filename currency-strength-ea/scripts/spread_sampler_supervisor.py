#!/usr/bin/env python3
"""Supervisor externo do spread_sampler.

Motivo (observado rodando): o terminal MT5 pode "pendurar" — o
spread_sampler fica vivo mas para de amostrar, sem erro. Um watchdog
in-process não resolve de forma confiável (mt5.shutdown() pode travar junto
com a thread pendurada). Um processo separado que mata e reinicia é à prova
de bala: TerminateProcess no Windows mata qualquer processo, pendurado ou
não.

O que faz: sobe o spread_sampler como subprocesso e, a cada ciclo, checa
no banco a idade da amostra mais recente. Se passar de STALE_LIMIT sem
amostra nova (ou o subprocesso morrer), mata e sobe de novo. Se ficar
reiniciando à toa (ex: fim de semana, mercado fechado e sem tick), espaça
as checagens para não encher o log.

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
STALE_LIMIT_SECONDS = 210            # ~7 ciclos de 30s sem amostra nova => reinicia
THRASH_WINDOW_SECONDS = 900
THRASH_MAX_RESTARTS = 4              # + de N reinícios na janela => modo lento
SLOW_CHECK_INTERVAL_SECONDS = 600


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


def main() -> None:
    log("supervisor iniciado")
    proc = spawn()
    started_at = time.monotonic()
    restart_times: list[float] = []

    try:
        while True:
            interval = CHECK_INTERVAL_SECONDS
            now_mono = time.monotonic()
            restart_times = [t for t in restart_times if now_mono - t < THRASH_WINDOW_SECONDS]
            if len(restart_times) >= THRASH_MAX_RESTARTS:
                interval = SLOW_CHECK_INTERVAL_SECONDS
                log(f"muitos reinícios ({len(restart_times)}) na última janela — checando a cada {interval}s")
            time.sleep(interval)

            reason = None
            if proc.poll() is not None:
                reason = f"subprocesso saiu (exit {proc.returncode})"
            elif time.monotonic() - started_at > GRACE_AFTER_START_SECONDS:
                latest = latest_sample_epoch()
                if latest is None:
                    reason = "sem nenhuma amostra no banco"
                else:
                    age = time.time() - latest
                    if age > STALE_LIMIT_SECONDS:
                        reason = f"amostra mais recente tem {age:.0f}s (limite {STALE_LIMIT_SECONDS}s)"

            if reason:
                log(f"REINICIANDO: {reason}")
                kill(proc)
                proc = spawn()
                started_at = time.monotonic()
                restart_times.append(time.monotonic())
    except KeyboardInterrupt:
        log("Ctrl+C — encerrando supervisor e spread_sampler")
        kill(proc)


if __name__ == "__main__":
    main()
