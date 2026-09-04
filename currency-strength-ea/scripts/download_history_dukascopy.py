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

Volume esperado: 28 pares × ~6-7 anos × 24 arquivos/dia ≈ 1.6-1.8 milhões de
requisições HTTP pequenas. A Dukascopy limita rajada (devolve 503/429 em
série e libera sozinha em ~1-2 min), então mesmo com --workers baixo isto é
um job de MUITAS horas, possivelmente 1-2 dias corridos — deixe rodando em
background e espere ele terminar sozinho. É resumível: re-rodar retoma de
onde parou (a menos que --no-resume seja passado).

O default de 4 workers é propositalmente conservador. Subir --workers acelera
até a Dukascopy começar a 503-ar; se vir muitos "AVISO: ... HTTP 503",
baixe. Se um par parar por falha de download ("BACKFILL INCOMPLETO" no fim),
é só re-rodar — ele retoma do dia que faltou, sem deixar buraco silencioso.

Uso:
    python -m scripts.download_history_dukascopy
    python -m scripts.download_history_dukascopy --pairs EURUSD,USDJPY --workers 6
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

# A Dukascopy limita rajada devolvendo 503/429 em série E travando a conexão
# (read timeout) — testado: são a mesma causa (carga), e liberam sozinhas em
# ~1-2 min. Então 5xx e erro de rede COMPARTILHAM um orçamento único de
# insistência (~15 min por hora): o fetch retenta com backoff (respeitando
# Retry-After) até esse teto antes de desistir. Desistir significa outage/hora
# quebrada de verdade — e aí o chamador para o par, em vez de deixar buraco
# silencioso no histórico.
THROTTLE_STATUSES = frozenset({429, 500, 502, 503, 504})
BACKOFF_BASE_SECONDS = 5.0
BACKOFF_CAP_SECONDS = 120.0
GIVE_UP_SECONDS = 900  # ~15 min de 5xx/timeout contínuo na MESMA hora => desiste
CONNECT_TIMEOUT_SECONDS = 15
READ_TIMEOUT_SECONDS = 60  # .bi5 de hora movimentada + servidor sob carga


def _backoff(attempt: int) -> float:
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt)) + random.uniform(0, 3)


def _retry_delay(resp: requests.Response, attempt: int) -> float:
    """Prioriza o header Retry-After (numérico ou data HTTP); sem ele, backoff
    exponencial com teto e jitter (evita os workers voltarem a bater juntos)."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            try:
                when = parsedate_to_datetime(retry_after)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
                if delay > 0:
                    return min(delay, GIVE_UP_SECONDS)
            except (TypeError, ValueError):
                pass
    return _backoff(attempt)


def _fetch_hour(session: requests.Session, pair: str, dt_hour: datetime) -> bytes | None:
    """Bytes do .bi5 (b'' = 404/hora sem arquivo), ou None se após ~15 min de
    5xx/timeout na mesma hora não deu — o chamador para o par (sem gap mudo)."""
    url = bi5_url(pair, dt_hour)
    attempt = 0
    waited = 0.0
    while True:
        try:
            resp = session.get(url, timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS))
        except requests.RequestException as exc:
            if waited >= GIVE_UP_SECONDS:
                print(f"  AVISO: {url}: desistindo após {waited:.0f}s ({exc.__class__.__name__})", file=sys.stderr)
                return None
            wait = _backoff(attempt)
            if attempt == 3 or attempt % 20 == 0:
                print(
                    f"  AVISO: {url}: {exc.__class__.__name__}, backoff {wait:.0f}s "
                    f"(insistindo há {waited:.0f}s)",
                    file=sys.stderr,
                )
            attempt += 1
            waited += wait
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            return b""  # par/data sem arquivo — hora sem tick
        if resp.status_code == 200:
            return resp.content
        if resp.status_code in THROTTLE_STATUSES:
            if waited >= GIVE_UP_SECONDS:
                print(
                    f"  AVISO: {url} -> HTTP {resp.status_code} por >{GIVE_UP_SECONDS // 60} min, desistindo",
                    file=sys.stderr,
                )
                return None
            wait = _retry_delay(resp, attempt)
            if attempt == 3 or attempt % 20 == 0:
                print(
                    f"  AVISO: {url} -> HTTP {resp.status_code}, backoff {wait:.0f}s "
                    f"(insistindo há {waited:.0f}s)",
                    file=sys.stderr,
                )
            attempt += 1
            waited += wait
            time.sleep(wait)
            continue

        print(f"  AVISO: {url} -> HTTP {resp.status_code} inesperado, tratando como não baixado", file=sys.stderr)
        return None


def _download_day(
    session: requests.Session, executor: ThreadPoolExecutor, pair: str, day: datetime
) -> tuple[list[tuple], list[datetime]]:
    hours = [day.replace(hour=h, minute=0, second=0, microsecond=0) for h in range(24)]
    futures = {executor.submit(_fetch_hour, session, pair, h): h for h in hours}

    all_rows: list[tuple] = []
    failed_hours: list[datetime] = []
    for future in as_completed(futures):
        dt_hour = futures[future]
        raw = future.result()
        if raw is None:
            failed_hours.append(dt_hour)
            continue
        ticks = decode_bi5(raw, pair)
        if not ticks:
            continue
        all_rows.extend(ticks_to_m5_candles(pair, hour_start_epoch(dt_hour), ticks))

    all_rows.sort(key=lambda r: r[0])
    return all_rows, failed_hours


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
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", dest="resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    args = parser.parse_args()

    pairs = args.pairs.split(",") if args.pairs else config.PAIRS
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else datetime.now(timezone.utc)

    conn = db.connect(config.DB_PATH)
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    halted_pairs: list[tuple[str, object]] = []

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
                rows, failed_hours = _download_day(session, executor, pair, day)
                if rows:
                    db.insert_candles(conn, symbol_id, rows)
                    total_candles += len(rows)
                if failed_hours:
                    print(
                        f"  {day.date()}: {len(rows)} candles M5 salvos, mas {len(failed_hours)} "
                        f"hora(s) NÃO baixada(s) — parando {pair} aqui. Re-rode o script "
                        f"para retomar deste dia (é resumível/upsert).",
                        file=sys.stderr,
                    )
                    halted_pairs.append((pair, day.date()))
                    break
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

    if halted_pairs:
        print("\n" + "=" * 64, file=sys.stderr)
        print("BACKFILL INCOMPLETO — pares parados por falha de download:", file=sys.stderr)
        for pair, day in halted_pairs:
            print(f"  {pair}: retomar a partir de {day}", file=sys.stderr)
        print("Re-rode `python -m scripts.download_history_dukascopy` para continuar.", file=sys.stderr)
        sys.exit(1)

    print("\nBackfill completo — todos os pares cobertos até a data pedida.")


if __name__ == "__main__":
    main()
