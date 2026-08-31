import time

from fastapi import APIRouter, Depends
from sentinel_observability import PAYMENT_DURATION, PAYMENTS_FAILED, PAYMENTS_TOTAL
from sqlalchemy.orm import Session

from sentinel_common.db import get_session
from sentinel_common.models import Payment
from sentinel_contracts.orders import CreatePaymentRequest, PaymentResponse

router = APIRouter()


def _create_payment(
    payload: CreatePaymentRequest,
    session: Session,
    status: str,
) -> PaymentResponse:
    started = time.perf_counter()
    try:
        payment = Payment(
            order_id=payload.order_id,
            status=status,
            amount=payload.amount,
        )
        session.add(payment)
        session.commit()
        session.refresh(payment)
        PAYMENTS_TOTAL.labels(status=status).inc()
        if status == "FAILED":
            PAYMENTS_FAILED.inc()
        return PaymentResponse(
            id=payment.id,
            order_id=payment.order_id,
            status=payment.status,
            amount=payment.amount,
            created_at=payment.created_at,
        )
    finally:
        PAYMENT_DURATION.observe(time.perf_counter() - started)


@router.post("/payments", response_model=PaymentResponse)
def create_payment(
    payload: CreatePaymentRequest,
    session: Session = Depends(get_session),
) -> PaymentResponse:
    return _create_payment(payload, session, status="SUCCESS")


@router.post("/payments/simulate-failure", response_model=PaymentResponse)
def simulate_payment_failure(
    payload: CreatePaymentRequest,
    session: Session = Depends(get_session),
) -> PaymentResponse:
    """Dev/test endpoint — persists FAILED. Not used by Orders happy path."""
    return _create_payment(payload, session, status="FAILED")
