"""Tests for the payment processing system."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'implementer'))

import pytest
from payment_system import PaymentSystem


@pytest.fixture
def ps():
    """Create a payment system with two funded accounts."""
    ps = PaymentSystem()
    ps.create_account("alice", "USD", initial_balance=1000)
    ps.create_account("bob", "USD", initial_balance=0)
    return ps


def test_successful_payment_and_balances(ps):
    """Test from the spec example: payment debits payer, credits payee."""
    payment = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="pay-001")
    assert payment.status == "COMPLETED"
    assert ps.get_balance("alice") == 900.0
    assert ps.get_balance("bob") == 100.0
    assert ps.verify_ledger_integrity()


def test_idempotency_prevents_double_charge(ps):
    """Same idempotency key returns same payment without re-processing."""
    p1 = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="pay-001")
    p2 = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="pay-001")
    assert p1.payment_id == p2.payment_id
    assert ps.get_balance("alice") == 900.0  # not charged twice


def test_failed_payment_no_balance_change(ps):
    """Failed processor doesn't affect balances."""
    ps.set_processor(lambda *args: {"status": "failure"})
    payment = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="fail-001")
    assert payment.status == "FAILED"
    assert ps.get_balance("alice") == 1000.0
    assert ps.get_balance("bob") == 0.0
    assert ps.verify_ledger_integrity()


def test_retry_on_timeout(ps):
    """Processor times out twice then succeeds on third attempt."""
    call_count = [0]
    def flaky_processor(*args):
        call_count[0] += 1
        if call_count[0] <= 2:
            return {"status": "timeout"}
        return {"status": "success"}

    ps.set_processor(flaky_processor)
    ps._base_delay = 0.01  # speed up test
    payment = ps.process_payment(50.0, "USD", "alice", "bob", idempotency_key="retry-001")
    assert payment.status == "COMPLETED"
    assert call_count[0] == 3
    assert ps.get_balance("alice") == 950.0


def test_full_and_partial_refund(ps):
    """Full and partial refunds create reverse ledger entries."""
    payment = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="ref-001")

    # Partial refund
    ps.refund(payment.payment_id, amount=40.0)
    assert ps.get_balance("alice") == 940.0
    assert ps.get_balance("bob") == 60.0

    # Another partial refund (remaining)
    ps.refund(payment.payment_id, amount=60.0)
    assert ps.get_balance("alice") == 1000.0
    assert ps.get_balance("bob") == 0.0
    assert ps.verify_ledger_integrity()


def test_refund_exceeding_amount_fails(ps):
    """Cannot refund more than the original payment amount."""
    payment = ps.process_payment(100.0, "USD", "alice", "bob", idempotency_key="over-001")
    with pytest.raises(ValueError, match="Refund exceeds"):
        ps.refund(payment.payment_id, amount=150.0)


def test_insufficient_balance_rejects(ps):
    """Payment fails when payer has insufficient funds."""
    payment = ps.process_payment(5000.0, "USD", "alice", "bob", idempotency_key="broke-001")
    assert payment.status == "FAILED"
    assert ps.get_balance("alice") == 1000.0


def test_currency_mismatch_rejects(ps):
    """Payment fails when currency doesn't match accounts."""
    ps.create_account("euro_user", "EUR", initial_balance=500)
    payment = ps.process_payment(100.0, "USD", "euro_user", "bob", idempotency_key="cur-001")
    assert payment.status == "FAILED"


def test_webhooks_fire(ps):
    """Webhook callbacks fire on payment events."""
    events = []
    ps.register_webhook("payment.created", lambda e, p: events.append(e))
    ps.register_webhook("payment.completed", lambda e, p: events.append(e))
    ps.register_webhook("payment.refunded", lambda e, p: events.append(e))

    payment = ps.process_payment(50.0, "USD", "alice", "bob", idempotency_key="wh-001")
    ps.refund(payment.payment_id)

    assert "payment.created" in events
    assert "payment.completed" in events
    assert "payment.refunded" in events


def test_payment_query(ps):
    """Query payments by account and status."""
    ps.process_payment(10.0, "USD", "alice", "bob", idempotency_key="q1")
    ps.set_processor(lambda *a: {"status": "failure"})
    ps.process_payment(20.0, "USD", "alice", "bob", idempotency_key="q2")

    all_payments = ps.get_payments(account_id="alice")
    assert len(all_payments) == 2

    completed = ps.get_payments(account_id="alice", status="COMPLETED")
    assert len(completed) == 1
    assert completed[0].amount == 10.0
