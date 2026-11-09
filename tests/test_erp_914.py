from pathlib import Path

import pytest

from rotamap.io import EntradaInvalida, OpcoesEntrada, ler_entrada
from rotamap.io.erp_914 import ler_erp_914, separar_uf

N_COLUNAS = 26

CABECALHO_PAGINA = [
    ";" * 25,
    "914 - Rentabilidade por Rota" + ";" * 23 + "01/02/2026 10:00;;",
    ";" * 23 + "Página:;;{pagina} de 2",
    ";" * 25,
    "Período de saída;;;;;Motorista" + ";" * 20,
    "Filtros;01/01/2026 a 31/01/2026;;;;Todos" + ";" * 20,
    ";" * 25,
]
CABECALHO_ROTA = (
    ";Seq. Rota;Praça;;;;Distanc.;;Populaçao;Qt. Clientes;Qt. Atendidos;;;Qt. Cargas;"
    "Qt. Ent.;;Vl. Total;Qt. Notas;;Peso Total; por Entrega;; por Kg;;Lucro (%);"
)


def _linha(campos: dict[int, str]) -> str:
    return ";".join(campos.get(i, "") for i in range(N_COLUNAS))


def _rota(rota_id: str, nome: str) -> str:
    return _linha({0: "ROTA:", 2: rota_id, 3: nome, 20: "Vl.Médio", 21: "Vl.Médio"})


def _parada(seq: int, municipio: str, valor: str, lucro: str = "15,00") -> str:
    campos = {1: str(seq), 2: "100", 3: municipio, 6: "320", 7: "45000", 9: "20", 11: "8"}
    campos |= {13: "12", 14: "8", 15: valor, 17: "30,00", 19: "1.500,50", 20: "1,0", 24: lucro}
    return _linha(campos)


def _total(qt: int) -> str:
    # a linha de total vem com as colunas deslocadas; o adaptador nao deve le-la
    return _linha({0: "Qt. praça:", 1: str(qt), 2: "Total da Rota:", 7: "999.999,", 15: "1,00"})


@pytest.fixture
def relatorio(tmp_path: Path) -> Path:
    linhas = [
        *[linha.format(pagina=1) for linha in CABECALHO_PAGINA],
        _rota("10", "NOROESTE PAULISTA "),
        CABECALHO_ROTA,
        _parada(3, "BIRIGUI - SP", "123.456,78"),
        _parada(1, "SANTOPOLIS DO AGUAPEI- SP", "4.321,09", lucro="-7,25"),
        _parada(2, "LAVRINHAS (SP)", "980,00"),
        _total(3),
        ";" * 25,
        *[linha.format(pagina=2) for linha in CABECALHO_PAGINA],
        _rota("11", "VALE"),
        CABECALHO_ROTA,
        _parada(1, "BONFIM PAULISTA - SP **", "10,00"),
        _parada(2, "SANTA RITA DO P. QUATRO  ", "20,00"),
        _total(2),
        "TOTAL:;;;;Qt. praça:;;5;42.073.524," + ";" * 18,
    ]
    caminho = tmp_path / "relatorio_914.csv"
    with caminho.open("w", encoding="mac_roman", newline="\r") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
    return caminho


def test_le_rotas_e_paradas(relatorio: Path) -> None:
    rotas = ler_erp_914(relatorio)

    assert [(r.id, r.nome) for r in rotas] == [("10", "NOROESTE PAULISTA"), ("11", "VALE")]
    assert [p.municipio for p in rotas[0].paradas] == [
        "BIRIGUI",
        "SANTOPOLIS DO AGUAPEI",
        "LAVRINHAS",
    ]
    assert [p.ordem for p in rotas[0].paradas] == [3, 1, 2]


def test_converte_numeros_no_padrao_brasileiro(relatorio: Path) -> None:
    birigui, santopolis, _ = ler_erp_914(relatorio)[0].paradas

    assert birigui.metricas["valor_total"] == pytest.approx(123456.78)
    assert birigui.metricas["peso_kg"] == pytest.approx(1500.5)
    assert santopolis.metricas["lucro_pct"] == pytest.approx(-7.25)


def test_ignora_medias_derivadas(relatorio: Path) -> None:
    metricas = ler_erp_914(relatorio)[0].paradas[0].metricas

    assert set(metricas) == {
        "distancia",
        "populacao",
        "clientes",
        "atendidos",
        "cargas",
        "entregas",
        "valor_total",
        "notas",
        "peso_kg",
        "lucro_pct",
    }


def test_municipio_sem_uf_assume_a_mais_comum(relatorio: Path) -> None:
    bonfim, santa_rita = ler_erp_914(relatorio)[1].paradas

    assert (bonfim.municipio, bonfim.uf) == ("BONFIM PAULISTA", "SP")
    assert (santa_rita.municipio, santa_rita.uf) == ("SANTA RITA DO P. QUATRO", "SP")


def test_uf_padrao_explicita_vale_para_quem_nao_tem_uf(relatorio: Path) -> None:
    rotas = ler_erp_914(relatorio, OpcoesEntrada(uf_padrao="mg"))

    assert rotas[1].paradas[1].uf == "MG"
    assert rotas[1].paradas[0].uf == "SP"


def test_via_registro_de_formatos(relatorio: Path) -> None:
    assert len(ler_entrada(relatorio, "erp_914")) == 2


def test_arquivo_sem_rotas(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.csv"
    caminho.write_text("a;b;c\n1;2;3\n", encoding="mac_roman")

    with pytest.raises(EntradaInvalida, match="nenhuma rota"):
        ler_erp_914(caminho)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("BIRIGUI - SP", ("BIRIGUI", "SP")),
        ("SANTOPOLIS DO AGUAPEI- SP", ("SANTOPOLIS DO AGUAPEI", "SP")),
        ("LAVRINHAS (SP)", ("LAVRINHAS", "SP")),
        ("BONFIM PAULISTA - SP **", ("BONFIM PAULISTA", "SP")),
        ("AGUAS DE SANTA BARBARA   ", ("AGUAS DE SANTA BARBARA", "")),
        ("SAO JOAO DO PAU D`ALHO", ("SAO JOAO DO PAU D`ALHO", "")),
        ("BIRITIBA-MIRIM - SP", ("BIRITIBA-MIRIM", "SP")),
        ("ALGUMA COISA - XX", ("ALGUMA COISA - XX", "")),
    ],
)
def test_separar_uf(texto: str, esperado: tuple[str, str]) -> None:
    assert separar_uf(texto) == esperado
