from pathlib import Path

import pytest

from rotamap.io import EntradaInvalida, OpcoesEntrada, ler_entrada
from rotamap.io.tidy import ler_tidy

CABECALHO = "rota_id,rota_nome,municipio,uf,cod_ibge,ordem,clientes,valor_total"


def _csv(tmp_path: Path, *linhas: str, encoding: str = "utf-8") -> Path:
    caminho = tmp_path / "rotas.csv"
    caminho.write_text("\n".join(linhas) + "\n", encoding=encoding)
    return caminho


def test_le_rotas_paradas_e_metricas(tmp_path: Path) -> None:
    caminho = _csv(
        tmp_path,
        CABECALHO,
        "1,Oeste,Birigui,SP,3506508,2,10,1500.50",
        "1,Oeste,Araçatuba,sp,,1,20,",
        "2,Leste,Atibaia,SP,,,5,300",
    )

    oeste, leste = ler_tidy(caminho)

    assert (oeste.id, oeste.nome, leste.id) == ("1", "Oeste", "2")
    araçatuba, birigui = oeste.paradas
    assert (araçatuba.municipio, araçatuba.uf, araçatuba.ordem) == ("Araçatuba", "SP", 1)
    assert araçatuba.metricas == {"clientes": 20.0}
    assert birigui.cod_ibge == "3506508"
    assert birigui.metricas == {"clientes": 10.0, "valor_total": 1500.5}


def test_so_colunas_obrigatorias(tmp_path: Path) -> None:
    caminho = _csv(tmp_path, "rota_id,rota_nome,municipio,uf", "7,Centro,Campinas,SP")

    (rota,) = ler_tidy(caminho)

    assert rota.paradas[0].ordem is None
    assert rota.paradas[0].metricas == {}


def test_paradas_sem_ordem_vao_para_o_fim_na_ordem_do_arquivo(tmp_path: Path) -> None:
    caminho = _csv(
        tmp_path,
        "rota_id,rota_nome,municipio,uf,ordem",
        "1,R,C,SP,",
        "1,R,A,SP,2",
        "1,R,D,SP,",
        "1,R,B,SP,1",
    )

    assert [p.municipio for p in ler_tidy(caminho)[0].paradas] == ["B", "A", "C", "D"]


def test_cabecalho_com_bom_maiusculas_e_espacos(tmp_path: Path) -> None:
    caminho = _csv(
        tmp_path, " Rota_ID , ROTA_NOME,Municipio,UF", "1,R,Birigui,SP", encoding="utf-8-sig"
    )

    assert ler_tidy(caminho)[0].paradas[0].municipio == "Birigui"


def test_padrao_brasileiro_com_ponto_e_virgula(tmp_path: Path) -> None:
    caminho = _csv(tmp_path, "rota_id;rota_nome;municipio;uf;valor", "1;R;Birigui;SP;1.234,56")

    rotas = ler_tidy(caminho, OpcoesEntrada(sep=";", decimal=","))

    assert rotas[0].paradas[0].metricas["valor"] == pytest.approx(1234.56)


def test_coluna_obrigatoria_ausente(tmp_path: Path) -> None:
    caminho = _csv(tmp_path, "rota_id,municipio", "1,Birigui")

    with pytest.raises(EntradaInvalida, match="rota_nome") as erro:
        ler_tidy(caminho)

    assert len(erro.value.problemas) == 2


def test_reune_todos_os_problemas_com_numero_da_linha(tmp_path: Path) -> None:
    caminho = _csv(
        tmp_path,
        CABECALHO,
        "1,Oeste,Birigui,SP,,1,10,100",
        "1,Outro nome,Penápolis,SP,,2,10,100",
        "1,Oeste,birigui,SP,,3,10,100",
        "2,Leste,Atibaia,XX,,1,10,100",
        "2,Leste,Bragança,SP,123,2,10,100",
        "2,Leste,Vargem,SP,,dois,10,100",
        "2,Leste,Piracaia,SP,,3,muitos,100",
        "2,Leste,,SP,,4,10,100",
        "2,Leste,Joanópolis,SP",
    )

    with pytest.raises(EntradaInvalida) as erro:
        ler_tidy(caminho)

    problemas = erro.value.problemas
    assert [p.split(":")[0] for p in problemas] == [f"linha {n}" for n in range(3, 11)]
    assert "nome 'Outro nome'" in problemas[0]
    assert "repetido" in problemas[1]
    assert "uf inválida" in problemas[2]
    assert "7 dígitos" in problemas[3]
    assert "ordem" in problemas[4]
    assert "'clientes' não numérica" in problemas[5]
    assert "municipio" in problemas[6]
    assert "colunas" in problemas[7]


def test_arquivo_sem_dados(tmp_path: Path) -> None:
    with pytest.raises(EntradaInvalida, match="nenhuma linha"):
        ler_tidy(_csv(tmp_path, CABECALHO, ""))


def test_formato_desconhecido(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="formato desconhecido"):
        ler_entrada(_csv(tmp_path, CABECALHO), "xlsx")
