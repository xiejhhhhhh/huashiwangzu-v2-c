from pydantic import BaseModel


class SaveMemoryRequest(BaseModel):
    text: str
    tags: str | None = None
    source: str | None = None
    conversation_id: int | None = None


class RecallRequest(BaseModel):
    query: str
    limit: int = 5
    expand_chain: bool = False


class DeleteMemoryRequest(BaseModel):
    id: int


class FuseRequest(BaseModel):
    query: str
    ids: list[int]


class RethinkRequest(BaseModel):
    id: int
    text: str
    tags: str | None = None


class ReplaceRequest(BaseModel):
    id: int
    old_text: str
    new_text: str


class InsertRequest(BaseModel):
    id: int
    text: str
