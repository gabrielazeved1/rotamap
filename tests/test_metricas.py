import pytest

from rotamap.metricas import (
    MUNICIPIOS,
    PRESETS,
    Agregacao,
    Formato,
    Metrica,
    agregar,
    calcular,
    formatar,
    metricas_padrao,
)
from rotamap.models import Parada, Rota


def _parada(municipio: str, cod: str | None = None, **metricas: float) -> Parada:
    return Parada(municipio, "SP", cod_ibge=cod, metricas=metricas)


PARADAS = [
    _parada("Campinas Norte", "3509502", valor=1000.0, entregas=10, margem=10.0),
    _parada("Campinas Sul", "3509502", valor=3000.0, entregas=20, margem=20.0),
    _parada("Atibaia", "3504107", valor=1000.0, entregas=0, margem=5.0),
    _parada("Sem dados"),
]


@pytest.mark.parametrize(
    ("metrica", "esperado"),
    [
        (MUNICIPIOS, 3),
        (Metrica("v", "valor"), 5000),
        (Metrica("v", "valor", Agregacao.MEDIA), 5000 / 3),
        (Metrica("m", "margem", Agregacao.PONDERADA, peso="valor"), 15.0),
        (Metrica("t", "valor", Agregacao.RAZAO, por="entregas"), 5000 / 30),
        (Metrica("x", "inexistente"), None),
        (Metrica("x", "inexistente", Agregacao.MEDIA), None),
    ],
)
def test_agregar(metrica: Metrica, esperado: float | None) -> None:
    resultado = agregar(PARADAS, metrica)

    assert resultado == (None if esperado is None else pytest.approx(esperado))


def test_razao_com_denominador_zero() -> None:
    metrica = Metrica("t", "valor", Agregacao.RAZAO, por="entregas")

    assert agregar([PARADAS[2]], metrica) is None


def test_contagem_sem_codigo_usa_o_nome() -> None:
    paradas = [_parada("Birigui"), _parada("BIRIGUI"), _parada("Penápolis")]

    assert agregar(paradas, MUNICIPIOS) == 2


@pytest.mark.parametrize(
    ("valor", "formato", "casas", "esperado"),
    [
        (1234567.891, Formato.MOEDA, 2, "R$ 1.234.567,89"),
        (1234567.891, Formato.MOEDA, 0, "R$ 1.234.568"),
        (-1500.0, Formato.MOEDA, 0, "-R$ 1.500"),
        (15.784, Formato.PERCENTUAL, 1, "15,8%"),
        (1234.6, Formato.INTEIRO, 2, "1.235"),
        (0.5, Formato.NUMERO, 2, "0,50"),
        (-0.001, Formato.NUMERO, 2, "0,00"),
        (None, Formato.MOEDA, 2, "–"),
    ],
)
def test_formatar(valor: float | None, formato: Formato, casas: int, esperado: str) -> None:
    assert formatar(valor, Metrica("x", "x", formato=formato, casas=casas)) == esperado


@pytest.mark.parametrize(
    ("argumentos", "erro"),
    [
        ({"rotulo": "x"}, "coluna"),
        ({"rotulo": "x", "coluna": "a", "agregacao": Agregacao.PONDERADA}, "peso"),
        ({"rotulo": "x", "coluna": "a", "agregacao": Agregacao.RAZAO}, "denominador"),
    ],
)
def test_metrica_invalida(argumentos: dict[str, object], erro: str) -> None:
    with pytest.raises(ValueError, match=erro):
        Metrica(**argumentos)  # type: ignore[arg-type]


def test_metricas_padrao_soma_cada_coluna() -> None:
    rotas = [Rota("1", "R", [_parada("A", valor=1.5, clientes=2), _parada("B", clientes=3)])]

    metricas = metricas_padrao(rotas)

    assert metricas[0] == MUNICIPIOS
    assert [(m.rotulo, m.coluna, m.casas) for m in metricas[1:]] == [
        ("Valor", "valor", 2),
        ("Clientes", "clientes", 0),
    ]


def test_preset_do_erp_914_reproduz_os_totais_do_relatorio() -> None:
    # duas paradas inventadas com as colunas que o adaptador gera
    paradas = [
        Parada(
            "A",
            "SP",
            metricas={"atendidos": 30, "entregas": 30, "valor_total": 90000.0, "lucro_pct": 10.0},
        ),
        Parada(
            "B",
            "SP",
            metricas={"atendidos": 10, "entregas": 10, "valor_total": 10000.0, "lucro_pct": 30.0},
        ),
    ]

    assert calcular(paradas, PRESETS["erp_914"]) == [
        ("Municípios", "2"),
        ("Clientes atendidos", "40"),
        ("Entregas", "40"),
        ("Faturamento", "R$ 100.000"),
        ("Valor por entrega", "R$ 2.500"),
        ("Margem", "12,0%"),
    ]
