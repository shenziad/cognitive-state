"""Local representation counts are distinct from provider billed tokens."""


class RepresentationCounter:
    def __init__(self, name: str):
        self.name = name
        self.encoding = None
        if name.startswith("tiktoken:"):
            try:
                import tiktoken
            except ImportError:
                raise ValueError("Install the api optional dependency for tiktoken counting") from None
            self.encoding = tiktoken.get_encoding(name.split(":", 1)[1])
        elif name != "utf8_bytes":
            raise ValueError("counter must be utf8_bytes (mock) or tiktoken:<encoding>")

    def count(self, text: str) -> int:
        if self.encoding is not None:
            return len(self.encoding.encode(text, disallowed_special=()))
        return len(text.encode("utf-8"))
