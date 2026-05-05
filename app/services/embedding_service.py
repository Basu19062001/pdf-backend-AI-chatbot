class EmbeddingService:
    def create_embedding(self, text: str) -> list[float]:
        return [float(len(text))]
