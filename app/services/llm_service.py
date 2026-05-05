class LLMService:
    def answer_question(self, question: str, context: list[str] | None = None) -> str:
        snippets = context or []
        if not snippets:
            return f"Answer placeholder for: {question}"
        return f"Answer placeholder for: {question}\nContext snippets used: {len(snippets)}"
