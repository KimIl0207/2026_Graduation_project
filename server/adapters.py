class InMemoryUploadFile:
    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self._content
