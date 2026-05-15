from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class LoginResponse(BaseModel):
    message: str = "Login successful"
