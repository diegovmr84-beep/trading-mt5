"""Wrapper fino sobre o pacote `MetaTrader5`.

O pacote `MetaTrader5` só existe para Windows (é um binding para o terminal
MT5, que roda nativamente só em Windows). Por isso o import é feito de
forma lazy (dentro de `connect()`), para que o resto do projeto (geração de
pares, schema do banco, testes) possa ser importado e testado em qualquer
SO, sem exigir o terminal instalado.

Credenciais NUNCA ficam em código ou em config.py — vêm de variáveis de
ambiente:
    MT5_LOGIN      número da conta
    MT5_PASSWORD   senha da conta
    MT5_SERVER     nome do servidor (ex: "Exness-MT5Real8")
    MT5_PATH       (opcional) caminho do terminal64.exe, se não for o padrão
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class MT5ConnectionError(RuntimeError):
    pass


@contextmanager
def connect() -> Iterator["object"]:
    """Context manager: inicializa e faz login no terminal MT5, garante
    shutdown mesmo se algo falhar no meio do uso."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        raise MT5ConnectionError(
            "Pacote 'MetaTrader5' não encontrado ou não suportado neste SO. "
            "Este script precisa rodar numa máquina Windows com o terminal "
            "MT5 da Exness instalado e logado. Ver README.md."
        ) from exc

    login = os.environ.get("MT5_LOGIN")
    password = os.environ.get("MT5_PASSWORD")
    server = os.environ.get("MT5_SERVER")
    path = os.environ.get("MT5_PATH")  # opcional

    if not login or not password or not server:
        raise MT5ConnectionError(
            "Variáveis de ambiente MT5_LOGIN, MT5_PASSWORD e MT5_SERVER são "
            "obrigatórias. Ver README.md para instruções."
        )

    init_kwargs = {"login": int(login), "password": password, "server": server}
    if path:
        init_kwargs["path"] = path

    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        raise MT5ConnectionError(f"Falha ao inicializar/logar no MT5: {error}")

    try:
        yield mt5
    finally:
        mt5.shutdown()
