from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class CreateOrderRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    items: list[OrderItem] = Field(min_length=1)
    amount: int = Field(gt=0)


class CreateOrderResponse(BaseModel):
    id: UUID
    customer_id: str
    status: str
    amount: int
    payment_id: UUID | None = None
    created_at: datetime


class ReserveInventoryRequest(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class ReserveInventoryResponse(BaseModel):
    product_id: str
    reserved_quantity: int
    available_quantity: int


class InventoryResponse(BaseModel):
    product_id: str
    available_quantity: int
    cache_hit: bool = False


class CreatePaymentRequest(BaseModel):
    order_id: UUID
    amount: int = Field(gt=0)


class PaymentResponse(BaseModel):
    id: UUID
    order_id: UUID
    status: str
    amount: int
    created_at: datetime


class HealthResponse(BaseModel):
    service: str
    status: str
