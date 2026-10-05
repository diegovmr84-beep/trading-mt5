#!/usr/bin/env python3
"""Fase 4, item 9 — abre o período de VALIDAÇÃO (out-of-sample) UMA ÚNICA VEZ.

Aplica, sem reajuste nenhum, a configuração escolhida no desenvolvimento
(reports/fase4_dev_results.json) aos eventos de validação, com a mesma tabela
de stop/take calibrada só no desenvolvimento. A abertura é registrada em
`validation_lock` ANTES de qualquer resultado ser visto; uma segunda execução
é recusada.

Só rode isto depois de commitar fase4_dev_results.json e com aprovação do
usuário para gastar o out-of-sample.

Uso:
    python -m scripts.run_validation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import backtest_config as cfg
from src import db
from src.backtest import apply_scenario, simulate_trades
from src.backtest_io import (
    clear_trades, jsonable, load_events, open_validation_lock, save_trades,
)
from src.loaders import load_ohlc
from src.validation_stats import summarize


def main() -> None:
    dev = json.loads(Path("reports/fase4_dev_results.json").read_text(encoding="utf-8"))
    chosen = dev["chosen"]
    variant, k = chosen["variant"], int(chosen["k"])
    cid = chosen["config"]

    conn = db.connect(config.DB_PATH)
    open_validation_lock(conn, cid, "abertura única do OOS (Fase 4, item 9)")  # recusa se já aberta
    print(f"Validação aberta (única vez) para a configuração {cid}")

    ohlc = load_ohlc(conn)
    events = load_events(conn, variant, k, "val")
    gross = simulate_trades(events, ohlc, cfg.HORIZON)
    clear_trades(conn, "oos")
    scenarios = {}
    for name, scenario in cfg.SCENARIOS.items():
        net = apply_scenario(gross, scenario)
        scenarios[name] = summarize(net)
        save_trades(conn, net, "oos", cid, name, "val")
        print(f"  {name:10s}: {scenarios[name]}")
    out = {"config": cid, "n_events": len(events), "primary": scenarios[cfg.PRIMARY_SCENARIO], "scenarios": scenarios}
    Path("reports/fase4_oos_results.json").write_text(
        json.dumps(jsonable(out), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print("escrito reports/fase4_oos_results.json — agora rode scripts.make_fase4_report")
    conn.close()


if __name__ == "__main__":
    main()
