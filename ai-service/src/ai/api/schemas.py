from pydantic import BaseModel, ConfigDict, Field


class AiProviderIn(BaseModel):
    label: str
    kind: str = "custom"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    api_keys: list[str] = Field(default_factory=list)
    requires_api_key: bool = True


class AiProviderImportIn(AiProviderIn):
    """Bản sao từ translate, giữ id cũ để job đang trỏ không gãy."""

    id: int
    provider: str = "openai"


class AiProviderAddKeyIn(BaseModel):
    api_key: str


class AiProviderPatchIn(BaseModel):
    label: str | None = None
    kind: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_keys: list[str] | None = None
    requires_api_key: bool | None = None


class AiProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    kind: str
    provider: str
    base_url: str
    model: str
    requires_api_key: bool
    has_api_key: bool = False
    api_key_hint: str = ""
    api_key_hints: list[str] = Field(default_factory=list)
    key_count: int = 1
    sort_order: int = 0


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    provider_id: int
    messages: list[ChatMessageIn]
    temperature: float = 0.3
    model: str = ""
    # Chỉ dùng key thứ n (job dịch tự xoay). None = ai-service tự xoay.
    key_index: int | None = None
    # Service gọi vào (translate, write, tts) — chỉ để thống kê.
    caller: str = ""


class ChatOut(BaseModel):
    content: str


class UsageRow(BaseModel):
    key: str
    label: str = ""
    calls: int
    prompt_tokens: int
    completion_tokens: int


class UsageOut(BaseModel):
    days: int
    total: UsageRow
    by_day: list[UsageRow]
    by_provider: list[UsageRow]
    by_caller: list[UsageRow]
