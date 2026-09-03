"""Wrapper fino sobre o pacote `MetaTrader5`.

O pacote `MetaTrader5` só existe para Windows (é um binding para o terminal
MT5, que roda nativamente só em Windows). Por isso o import é feito de
forma lazy (dentro de `connect()`), para que o resto do projeto (geração de
pares, schema do banco, testes) possa ser importado e testado em qualquer
SO, sem exigir o terminal instalado.

Dois modos de conexão:

1. **Anexar ao terminal já aberto** (padrão quando não há credenciais no
   ambiente): o terminal MT5 precisa estar rodando e logado numa conta
   Exness. `mt5.initialize()` sem argumentos anexa à sessão existente e usa
   a conta em que o terminal já está logado. Nenhuma credencial passa pelo
   código.

2. **Login explícito por variável de ambiente** (usado se `MT5_LOGIN`,
   `MT5_PASSWORD` e `MT5_SERVER` estiverem todas definidas): útil em
   automação sem alguém logado manualmente no terminal. Credenciais NUNCA
   ficam em código ou em config.py — só no ambiente:
       MT5_LOGIN      número da conta
       MT5_PASSWORD   senha da conta
       MT5_SERVER     nome do servidor (ex: "Exness-MT5Trial11")
   Opcional em qualquer modo:
       MT5_PATH       caminho do terminal64.exe, se não for o padrão
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class MT5ConnectionError(RuntimeError):
    pass


@contextmanager
def connect() -> Iterator["object"]:
    """Context manager: conecta ao terminal MT5 (anexando à sessão aberta ou
    logando via env vars), garante shutdown mesmo se algo falhar no meio do
    uso."""
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

    have_credentials = bool(login and password and server)

    init_kwargs: dict[str, object] = {}
    if path:
        init_kwargs["path"] = path
    if have_credentials:
        # Modo 2: login explícito. `login` já foi checado como truthy acima.
        init_kwargs.update(login=int(login), password=password, server=server)  # type: ignore[arg-type]

    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        if have_credentials:
            hint = "Falha ao inicializar/logar no MT5"
        else:
            hint = (
                "Falha ao anexar ao terminal MT5. Verifique se o terminal MT5 "
                "da Exness está aberto e logado numa conta, ou defina "
                "MT5_LOGIN/MT5_PASSWORD/MT5_SERVER para login explícito. Ver README.md"
            )
        raise MT5ConnectionError(f"{hint}: {error}")

    try:
        # Sanidade: sem conta logada, não há como coletar nada.
        account = mt5.account_info()
        if account is None:
            raise MT5ConnectionError(
                "Terminal MT5 conectado mas sem conta logada "
                f"(last_error={mt5.last_error()}). Faça login no terminal "
                "ou defina MT5_LOGIN/MT5_PASSWORD/MT5_SERVER."
            )
        yield mt5
    finally:
        mt5.shutdown()
