"""Configuração do Currency Strength EA — Fase 1 (coleta de dados).

Nenhuma credencial fica neste arquivo. Login, senha e servidor do MT5 vêm
de variáveis de ambiente (ver README.md).
"""

from __future__ import annotations

import os

from src.pairs import generate_pairs, with_broker_suffix

# --- Universo de moedas e pares -------------------------------------------------

MAJORS = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]

# Sufixo de símbolo da corretora (ex: Exness pode usar "EURUSDm" em vez de
# "EURUSD" dependendo do tipo de conta). Configurável via env var para não
# precisar editar código ao trocar de conta/corretora.
MT5_SYMBOL_SUFFIX = os.environ.get("MT5_SYMBOL_SUFFIX", "")

PAIRS = generate_pairs()  # 28 pares, sem sufixo — nomes "canônicos" usados no schema
MT5_SYMBOLS = with_broker_suffix(PAIRS, MT5_SYMBOL_SUFFIX)  # nomes reais a pedir ao MT5

# --- Histórico -------------------------------------------------------------------

HISTORY_START_UTC = "2020-01-01T00:00:00+00:00"
TIMEFRAME = "M5"

# Baixar em blocos anuais evita respostas gigantes numa única chamada ao MT5
# e facilita retomar uma coleta interrompida sem perder o que já foi salvo.
DOWNLOAD_CHUNK_DAYS = 365

# --- Banco de dados ---------------------------------------------------------------

DB_PATH = os.environ.get("CS_EA_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "currency_strength.db"))

# --- Amostragem de spread ao vivo --------------------------------------------------

SPREAD_SAMPLE_INTERVAL_SECONDS = int(os.environ.get("CS_EA_SPREAD_INTERVAL_S", "30"))
