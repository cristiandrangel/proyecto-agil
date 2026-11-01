import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", cleaned):
        raise ValueError("Use international E.164 phone format")
    return cleaned


class LocateRequest(StrictModel):
    phone_e164: str | None = None
    document_type: str | None = Field(None, min_length=1, max_length=20)
    document_number: str | None = Field(None, min_length=1, max_length=60)

    @field_validator("phone_e164")
    @classmethod
    def phone(cls, value):
        return normalize_phone(value) if value is not None else None

    @model_validator(mode="after")
    def exclusive(self):
        if bool(self.phone_e164) == bool(self.document_type and self.document_number):
            raise ValueError("Provide a phone OR complete document")
        if self.phone_e164 and (self.document_type or self.document_number):
            raise ValueError("Phone and document are exclusive")
        return self


class VerifyRequest(StrictModel):
    candidate_reference: UUID
    pin: str = Field(min_length=1, max_length=32, repr=False)
    binding_ref: UUID
    source_message_id: str = Field(min_length=1, max_length=200)
    confirmed: bool = True


class CustomerPatch(StrictModel):
    expected_contact_version: int = Field(ge=1)
    display_name: str | None = Field(None, min_length=1, max_length=120)
    phone_e164: str | None = None
    email: str | None = Field(None, max_length=200)
    delivery_mode: Literal["simulated", "live"] | None = None
    test_contact_enabled: bool | None = None
    customer_type: str | None = Field(None, min_length=1, max_length=30)

    @field_validator("phone_e164")
    @classmethod
    def phone(cls, value):
        return normalize_phone(value) if value is not None else None


class DebtPatch(StrictModel):
    expected_version: int = Field(ge=1)
    dias_mora: int | None = Field(None, ge=0)
    service_type: str | None = Field(None, min_length=1, max_length=50)
    due_date: date | None = None
    balance_cents: int | None = Field(None, ge=0, strict=True)
    service_status: str | None = Field(None, min_length=1, max_length=30)


class OrderRequest(StrictModel):
    debt_id: UUID
    expected_version: int = Field(ge=1)


class QuoteRequest(OrderRequest):
    offer_amount_usd: str = Field(strict=True)
    source_message_id: str = Field(min_length=1, max_length=200)
    currency: Literal["USD"] = "USD"


class AcceptRequest(StrictModel):
    expected_version: int = Field(ge=1)
    source_message_id: str = Field(min_length=1, max_length=200)


class AttemptRequest(StrictModel):
    capability: str = Field(min_length=1, repr=False)
    decision: Literal["approved", "rejected"]


class ResetRequest(StrictModel):
    confirmation: Literal["RESET_DEMO"]
    backend_reset_confirmed: Literal[True]
    epoch: UUID


class RevokeRequest(StrictModel):
    binding_ref: UUID
