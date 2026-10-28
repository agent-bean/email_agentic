class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class ToolDenied(Exception):
    def __init__(self, gate: str):
        self.gate = gate
        super().__init__(gate)


class ProviderFailure(Exception):
    def __init__(
        self, provider: str, transient: bool = False, ambiguous: bool = False, category: str = "unspecified"
    ):
        self.category = category
        self.provider = provider
        self.transient = transient
        self.ambiguous = ambiguous
        super().__init__(f"{provider} request failed")
