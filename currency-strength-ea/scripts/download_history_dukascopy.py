#!/usr/bin/env python3
"""Fase 1, item 1-2 (fonte alternativa): baixa histórico M5 2020+ dos 28
pares a partir do tick history público da Dukascopy, em vez do MT5.

Por quê: a conta MT5 Trial disponível não tem histórico M5 anterior a
~2025-05 (limitação da própria conta, não do código — ver
reports/fase1_relatorio.md). Este script não depende de MT5/Windows, só de
`requests` — roda em qualquer SO com acesso normal à internet.

IMPORTANTE — rode scripts/dukascopy_smoke_test.py numa hora/par conhecido
ANTES de disparar isto para o histórico completo, e confira visualmente que
os preços saem plausíveis. A lógica de decodificação (src/dukascopy.py) não
pôde ser validada contra um arquivo real no ambiente onde foi escrita.

Volume esperado: 28 pares × ~5-6 anos × 24 arquivos/dia ≈ 1.4-1.6 milhões de
requisições HTTP pequenas. Com concorrência (--workers, default 6) e as
noites/fins de semana retornando corpo vazio rapidamente, uma estimativa
grosseira é de algumas horas de execução — deixe rodando em background.
É resumível: re-rodar pula pares/dias já cobertos no banco (a menos que
--no-resume seja passado).

O default de 6 workers é propositalmente conservador: a Dukascopy devolve
429 (Too Many Requests) sob rajada. Se rodar estável por um bom tempo, dá
para subir com --workers; se começar a ver muitos "AVISO: HTTP 429", baixe.

Uso:
    python -m scripts.download_history_dukascopy
    python -m scripts.download_history_dukascopy --pairs EURUSD,USDJPY --workers 10
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.dukascopy import (
    REQUEST_HEADERS,
    bi5_url,
    decode_bi5,
    hour_start_epoch,
    ticks_to_m5_candles,
)
from src.gaps import detect_and_log_gaps
from src.pairs import split_pair

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 1.5  # erro de rede/timeout: backoff linear curto
# 429 (Too Many Requests): a Dukascopy é sensível a rajada e pode devolver 429
# em série. Backoff dedicado, exponencial e bem mais longo que o de erro de
# rede — e respeitando o header Retry-After quando o servidor o manda.
RATE_LIMIT_BACKOFF_SECONDS = 10.0
RATE_LIMIT_BACKOFF_CAP_SECONDS = 120.0


def _rate_limit_delay(resp: requests.Response, attempt: int) -> float:
    """Segundos a esperar após um 429, priorizando o header Retry-After
    (formato numérico ou data HTTP); sem ele, backoff exponencial com teto e
    jitter (evita os workers baterem no limite de novo todos juntos)."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            try:
                when = parsedate_to_datetime(retry_after)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
                if delay > 0:
                    return delay
            except (TypeError, ValueError):
                pass
    backoff = min(RATE_LIMIT_BACKOFF_CAP_SECONDS, RATE_LIMIT_BACKOFF_SECONDS * (2 ** attempt))
    return backoff + random.uniform(0, 3)


def _fetch_hour(session: requests.Session, pair: str, dt_hour: datetime) -> bytes:
    url = bi5_url(pair, dt_hour)
    last_problem: object = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            last_problem = exc
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        if resp.status_code == 404:
            return b""  # par/data sem arquivo — tratado como hora sem tick
        if resp.status_code == 200:
            return resp.content

        last_problem = f"HTTP {resp.status_code}"
        if resp.status_code == 429:
            wait = _rate_limit_delay(resp, attempt)
        else:
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
        print(
            f"  AVISO: {url} -> HTTP {resp.status_code}, aguardando {wait:.0f}s "
            f"(tentativa {attempt + 1}/{MAX_RETRIES})",
            file=sys.stderr,
        )
        time.sleep(wait)

    print(f"  AVISO: falha ao baixar {url} após {MAX_RETRIES} tentativas: {last_problem}", file=sys.stderr)
    return b""


def _download_day(
    session: requests.Session, executor: ThreadPoolExecutor, pair: str, day: datetime
) -> list[tuple]:
    hours = [day.replace(hour=h, minute=0, second=0, microsecond=0) for h in range(24)]
    futures = {executor.submit(_fetch_hour, session, pair, h): h for h in hours}

    all_rows: list[tuple] = []
    for future in as_completed(futures):
        dt_hour = futures[future]
        raw = future.result()
        ticks = decode_bi5(raw, pair)
        if not ticks:
            continue
        rows = ticks_to_m5_candles(pair, hour_start_epoch(dt_hour), ticks)
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: r[0])
    return all_rows


def _resume_start_day(conn, symbol_id: int, configured_start: datetime) -> datetime:
    row = conn.execute(
        "SELECT MAX(ts_utc) FROM candles_m5 WHERE symbol_id = ?", (symbol_id,)
    ).fetchone()
    if row is None or row[0] is None:
        return configured_start
    last_ts = datetime.fromtimestamp(row[0], tz=timezone.utc)
    # Redownload do último dia já parcialmente coberto, por segurança (é upsert).
    resume_day = last_ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(configured_start, resume_day)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default=None, help="lista separada por vírgula (default: os 28 pares)")
    parser.add_argument("--start", default=config.HISTORY_START_UTC)
    parser.add_argument("--end", default=None, help="ISO 8601 (default: agora)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--resume", dest="resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    args = parser.parse_args()

    pairs = args.pairs.split(",") if args.pairs else config.PAIRS
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else datetime.now(timezone.utc)

    conn = db.connect(config.DB_PATH)
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for pair in pairs:
            base, quote = split_pair(pair)
            symbol_id = db.upsert_symbol(conn, pair, base, quote)

            pair_start = _resume_start_day(conn, symbol_id, start) if args.resume else start
            if pair_start > end:
                print(f"\n=== {pair}: já coberto até {end.date()}, pulando (use --no-resume para refazer) ===")
                continue

            print(f"\n=== {pair}: {pair_start.date()} -> {end.date()} ===")
            day = pair_start
            total_candles = 0

            while day <= end:
                rows = _download_day(session, executor, pair, day)
                if rows:
                    db.insert_candles(conn, symbol_id, rows)
                    total_candles += len(rows)
                print(f"  {day.date()}: {len(rows)} candles M5" + ("" if rows else " (mercado fechado ou sem dado)"))
                day += timedelta(days=1)

            # Gaps detectados sobre TODO o histórico já salvo do par (não só
            # o baixado nesta execução), para não perder gaps de execuções
            # anteriores ao retomar com --resume.
            all_ts = [
                r[0]
                for r in conn.execute(
                    "SELECT ts_utc FROM candles_m5 WHERE symbol_id = ? ORDER BY ts_utc", (symbol_id,)
                )
            ]
            db.delete_data_gaps_for_symbol(conn, symbol_id)
            gaps = detect_and_log_gaps(conn, symbol_id, [(ts,) for ts in all_ts])
            print(f"  total nesta execução: {total_candles} candles | gaps suspeitos (histórico completo): {gaps}")

    conn.close()


if __name__ == "__main__":
    main()
