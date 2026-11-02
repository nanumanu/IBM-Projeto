def brl(value: float) -> str:
    """Formata em reais no padrão brasileiro: R$ 46.234,08"""
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"
