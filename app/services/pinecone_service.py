class PineconeService:
    def upsert_vector(self, vector_id: str, values: list[float], metadata: dict | None = None) -> dict:
        return {"vector_id": vector_id, "dimensions": len(values), "metadata": metadata or {}}
