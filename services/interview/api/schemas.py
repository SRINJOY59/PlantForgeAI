"""Request bodies for the interview API."""

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    profile: dict


class TextRequest(BaseModel):
    text: str
