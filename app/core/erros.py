class ErroDeValidacao(ValueError):
    """Dado de entrada inválido; a mensagem é exibida ao usuário."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.campo = campo


class IndiceIndisponivel(RuntimeError):
    """Não foi possível obter a série de índices (API fora do ar e sem cache)."""
