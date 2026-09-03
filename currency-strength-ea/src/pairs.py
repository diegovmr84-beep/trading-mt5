"""Geração dos 28 pares cruzados a partir dos 8 majors.

Convenção de base/quote: usamos a ordem de precedência de mercado padrão
(a mesma usada pela maioria dos brokers e "currency strength meters"):

    EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY

Ou seja, entre duas moedas, a que aparece primeiro nessa lista é a base do
par (ex: EUR/USD, não USD/EUR; USD/JPY, não JPY/USD). Isso não é uma escolha
arbitrária: é a convenção com que os pares já são cotados no mercado e,
portanto, os símbolos que o MT5/Exness expõe.

A ordem de precedência importa para a Seção 3.0 do estudo (decomposição de
força via sistema de equações) porque o sinal do retorno de cada par
depende de qual moeda é base e qual é quote.
"""

from __future__ import annotations

CURRENCY_PRECEDENCE: list[str] = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]


def generate_pairs(currencies: list[str] | None = None) -> list[str]:
    """Retorna os 28 símbolos de par (sem sufixo de corretora), na convenção
    base/quote de mercado, na ordem de precedência definida acima."""
    currencies = currencies if currencies is not None else CURRENCY_PRECEDENCE
    pairs = []
    for i in range(len(currencies)):
        for j in range(i + 1, len(currencies)):
            pairs.append(f"{currencies[i]}{currencies[j]}")
    return pairs


def split_pair(pair: str) -> tuple[str, str]:
    """Decompõe um símbolo de 6 letras (ex: 'EURUSD') em (base, quote)."""
    if len(pair) != 6:
        raise ValueError(f"símbolo de par inválido: {pair!r}")
    return pair[:3], pair[3:]


def with_broker_suffix(pairs: list[str], suffix: str = "") -> list[str]:
    """Aplica o sufixo de símbolo da corretora (ex: Exness pode expor
    'EURUSDm' em vez de 'EURUSD' dependendo do tipo de conta)."""
    if not suffix:
        return list(pairs)
    return [p + suffix for p in pairs]
