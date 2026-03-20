from pydantic import BaseModel


class MessagePart(BaseModel):
    text: str


class TaskMessage(BaseModel):
    role: str
    parts: list[MessagePart]


class TaskRequest(BaseModel):
    id: str
    sessionId: str
    message: TaskMessage


class TaskStatus(BaseModel):
    state: str


class ArtifactPart(BaseModel):
    text: str


class Artifact(BaseModel):
    parts: list[ArtifactPart]


class TaskResponse(BaseModel):
    id: str
    sessionId: str
    status: TaskStatus
    artifacts: list[Artifact]
