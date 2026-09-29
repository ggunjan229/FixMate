"""Validated request schemas shared by the API routers."""
from typing import Literal
from pydantic import BaseModel, Field


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    phone: str = Field(min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["customer", "worker"] = "customer"
    language: Literal["en", "hi"] = "en"


class LoginInput(BaseModel):
    email: str
    password: str


class WorkerProfile(BaseModel):
    skills: list[str] = Field(min_length=1, max_length=8)
    experience_years: float = Field(ge=0, le=60)
    certifications: list[str] = Field(default_factory=list, max_length=12)
    hourly_rate: float = Field(ge=1, le=100000)
    price_type: Literal["per_visit", "per_hour", "per_day", "fixed"] = "per_visit"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=15, ge=1, le=100)
    bio: str = Field(default="", max_length=400)


class BookingInput(BaseModel):
    service: str
    description: str = Field(default="", max_length=600)
    scheduled_at: str
    address: str = Field(min_length=4, max_length=240)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    emergency: bool = False
    quantity: int = Field(default=1, ge=1, le=20)
    payment_method: Literal["cash", "demo_digital"] = "cash"


class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


class AssistantInput(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    language: Literal["en", "hi"] = "en"
