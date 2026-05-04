from uuid import uuid4


def generate_entity_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"
