from dataclasses import dataclass

# 16:9 padrao do powerpoint, em polegadas
LARGURA = 13.333
ALTURA = 7.5
MARGEM = 0.4


@dataclass(frozen=True, slots=True)
class Caixa:
    """retangulo em polegadas a partir do canto superior esquerdo do slide."""

    x: float
    y: float
    largura: float
    altura: float

    @property
    def direita(self) -> float:
        return self.x + self.largura

    @property
    def base(self) -> float:
        return self.y + self.altura


@dataclass(frozen=True, slots=True)
class Tema:
    fundo: str = "#F4F6F8"
    texto: str = "#2C3E50"
    secundario: str = "#7F8C8D"
    cartao: str = "#FFFFFF"
    borda: str = "#DDE3E8"
    hotspot: str = "#1F1F1F"
    botao: str = "#2C3E50"
    fonte: str = "Calibri"


# capa: texto e resumo na esquerda, mapa na direita
CAPA_TITULO = Caixa(MARGEM + 0.2, 0.9, 4.4, 1.6)
CAPA_SUBTITULO = Caixa(MARGEM + 0.2, 2.5, 4.4, 0.5)
CAPA_RESUMO = Caixa(MARGEM + 0.2, 3.2, 4.4, 2.9)
CAPA_BOTAO = Caixa(MARGEM + 0.2, 6.35, 2.4, 0.5)
CAPA_MAPA = Caixa(5.1, MARGEM, LARGURA - 5.1 - MARGEM, ALTURA - 2 * MARGEM)

# menu: mapa clicavel e grade com todas as rotas
MENU_TITULO = Caixa(MARGEM, 0.25, 8.0, 0.6)
MENU_MAPA = Caixa(MARGEM, 1.0, 8.9, ALTURA - 1.0 - MARGEM)
MENU_GRADE = Caixa(9.6, 1.0, LARGURA - 9.6 - MARGEM, ALTURA - 1.0 - MARGEM)

# slide de rota: mapa na esquerda, kpis e cidades na direita
ROTA_VOLTAR = Caixa(MARGEM, 0.3, 1.1, 0.42)
ROTA_TITULO = Caixa(MARGEM + 1.3, 0.22, 8.4, 0.6)
ROTA_NAVEGACAO = Caixa(LARGURA - MARGEM - 2.3, 0.3, 2.3, 0.42)
ROTA_FAIXA = Caixa(MARGEM, 0.95, LARGURA - 2 * MARGEM, 0.06)
ROTA_MAPA = Caixa(MARGEM, 1.25, 6.5, 5.8)
ROTA_KPIS = Caixa(7.25, 1.25, LARGURA - 7.25 - MARGEM, 2.2)
ROTA_CIDADES = Caixa(7.25, 3.7, LARGURA - 7.25 - MARGEM, ALTURA - 3.7 - MARGEM)
