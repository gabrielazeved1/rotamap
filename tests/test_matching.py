import pytest

from rotamap.geo.malha import Distrito, Municipio
from rotamap.geo.matching import Matcher, Metodo, normalizar

CAMPINAS = Municipio("3509502", "Campinas", "SP")
CAMPINA = Municipio("3509106", "Campina do Monte Alegre", "SP")
RIBEIRAO = Municipio("3543402", "Ribeirão Preto", "SP")
SBO = Municipio("3545803", "Santa Bárbara d'Oeste", "SP")
EUCLIDES = Municipio("3515152", "Euclides da Cunha Paulista", "SP")
SAO_PAULO = Municipio("3550308", "São Paulo", "SP")
SAO_PAULO_POTENGI = Municipio("2412500", "São Paulo do Potengi", "RN")
SANTA_ISABEL = Municipio("3546801", "Santa Isabel", "SP")
SANTA_ISABEL_IVAI = Municipio("4123402", "Santa Isabel do Ivaí", "PR")
SANTA_ISABEL_PARA = Municipio("1506500", "Santa Izabel do Pará", "PA")

MUNICIPIOS = [
    CAMPINAS,
    CAMPINA,
    RIBEIRAO,
    SBO,
    EUCLIDES,
    SAO_PAULO,
    SAO_PAULO_POTENGI,
    SANTA_ISABEL,
    SANTA_ISABEL_IVAI,
    SANTA_ISABEL_PARA,
]
DISTRITOS = [
    Distrito("Bonfim Paulista", RIBEIRAO),
    Distrito("Joaquim Egídio", CAMPINAS),
    Distrito("Joaquim Egídio", SAO_PAULO),
]


@pytest.fixture
def matcher() -> Matcher:
    aliases = {
        "Balcão": None,
        "Centro de distribuição": "3509502",
        "Capital": "são paulo",
        "Errado": "Cidade que não existe",
    }
    return Matcher(MUNICIPIOS, DISTRITOS, aliases)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Ribeirão Preto", "RIBEIRAO PRETO"),
        ("  são   paulo ", "SAO PAULO"),
        ("Santa Bárbara d'Oeste", "SANTA BARBARA DOESTE"),
        ("SANTA BARBARA D\u2019OESTE", "SANTA BARBARA DOESTE"),
        ("SANTA BARBARA D\u00b4OESTE", "SANTA BARBARA DOESTE"),
        ("SAO JOAO DO PAU D`ALHO", "SAO JOAO DO PAU DALHO"),
        ("Biritiba-Mirim", "BIRITIBA MIRIM"),
        ("Embu-Guaçu", "EMBU GUACU"),
        ("SANTA RITA DO P. QUATRO", "SANTA RITA DO P QUATRO"),
    ],
)
def test_normalizar(entrada: str, esperado: str) -> None:
    assert normalizar(entrada) == esperado


def test_exato_ignora_acento_e_caixa(matcher: Matcher) -> None:
    resultado = matcher.associar("RIBEIRAO PRETO", "SP")

    assert (resultado.metodo, resultado.municipio) == (Metodo.EXATO, RIBEIRAO)


def test_exato_com_apostrofo_ausente(matcher: Matcher) -> None:
    assert matcher.associar("SANTA BARBARA DOESTE", "SP").municipio == SBO


def test_respeita_a_uf(matcher: Matcher) -> None:
    assert matcher.associar("Santa Isabel", "SP").municipio == SANTA_ISABEL
    assert matcher.associar("Sao Paulo do Potengi", "RN").municipio == SAO_PAULO_POTENGI


def test_codigo_tem_prioridade_sobre_o_nome(matcher: Matcher) -> None:
    resultado = matcher.associar("qualquer coisa", "SP", cod_ibge="3509502")

    assert (resultado.metodo, resultado.municipio) == (Metodo.CODIGO, CAMPINAS)


def test_codigo_fora_da_malha(matcher: Matcher) -> None:
    resultado = matcher.associar("Campinas", "SP", cod_ibge="9999999")

    assert resultado.metodo is Metodo.NAO_ENCONTRADO
    assert not resultado.encontrado


@pytest.mark.parametrize(
    ("entrada", "metodo", "municipio"),
    [
        ("BALCAO", Metodo.IGNORADO, None),
        ("centro de distribuicao", Metodo.ALIAS, CAMPINAS),
        ("Capital", Metodo.ALIAS, SAO_PAULO),
        ("errado", Metodo.NAO_ENCONTRADO, None),
    ],
)
def test_aliases(
    matcher: Matcher, entrada: str, metodo: Metodo, municipio: Municipio | None
) -> None:
    resultado = matcher.associar(entrada, "SP")

    assert (resultado.metodo, resultado.municipio) == (metodo, municipio)


def test_distrito_vira_o_municipio(matcher: Matcher) -> None:
    resultado = matcher.associar("BONFIM PAULISTA", "SP")

    assert (resultado.metodo, resultado.municipio) == (Metodo.DISTRITO, RIBEIRAO)


def test_distrito_ambiguo_nao_é_associado(matcher: Matcher) -> None:
    resultado = matcher.associar("Joaquim Egidio", "SP")

    assert resultado.metodo is Metodo.NAO_ENCONTRADO
    assert "Campinas" in resultado.detalhe and "São Paulo" in resultado.detalhe


def test_aproximado_acima_do_cutoff(matcher: Matcher) -> None:
    resultado = matcher.associar("CAMPINA DO M. ALEGRE", "SP")

    assert (resultado.metodo, resultado.municipio) == (Metodo.APROXIMADO, CAMPINA)
    assert resultado.score is not None and resultado.score >= 0.85


def test_nome_com_sufixo_do_erp(matcher: Matcher) -> None:
    resultado = matcher.associar("CAMPINAS NORTE", "SP")

    assert (resultado.metodo, resultado.municipio) == (Metodo.APROXIMADO, CAMPINAS)


def test_prefixo_mais_longo_vence() -> None:
    sao_jose = Municipio("1", "São José", "SC")
    sjc = Municipio("2", "São José dos Campos", "SC")

    resultado = Matcher([sao_jose, sjc]).associar("SAO JOSE DOS CAMPOS ZONA SUL", "SC")

    assert resultado.municipio == sjc


def test_nome_cortado_no_fim(matcher: Matcher) -> None:
    resultado = matcher.associar("EUCLIDES DA CUNHA", "SP")

    assert (resultado.metodo, resultado.municipio) == (Metodo.APROXIMADO, EUCLIDES)


def test_nome_cortado_ambiguo_nao_é_associado() -> None:
    municipios = [
        Municipio("1", "Santa Rosa do Sul", "SC"),
        Municipio("2", "Santa Rosa de Lima", "SC"),
    ]

    assert not Matcher(municipios).associar("Santa Rosa", "SC").encontrado


def test_nao_encontrado_sugere_o_mais_parecido(matcher: Matcher) -> None:
    resultado = matcher.associar("BALCAO RN SAO PAULO", "PR")

    assert resultado.metodo is Metodo.NAO_ENCONTRADO
    assert "Santa Isabel do Ivaí" in resultado.detalhe


def test_uf_fora_da_malha(matcher: Matcher) -> None:
    resultado = matcher.associar("Campinas", "MG")

    assert resultado.metodo is Metodo.NAO_ENCONTRADO
    assert "MG" in resultado.detalhe
