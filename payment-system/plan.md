# Plan (Iteration 1)

Task: Payment System
===============
SDI Vol 2 Reference: Chapter 11 - Payment System

Overview
--------
Build a payment processing system with idempotency, a payment state machine,
double-entry bookkeeping ledger, retry logic, refunds, and webhook
notifications. The system ensures exactly-once payment processing despite
retries and failures — critical for financial systems where duplicate charges
or lost payments are unacceptable.

Requirements
------------
1. Payment creation: create a payment with amount, currency, payer, payee,
   and an idempotency key.
2. Idempotency: if the same idempotency key is used, return the existing
   payment result without re-processing.
3. Payment state machine:
   CREATED → PROCESSING → COMPLETED (success)
   CREATED → PROCESSING → FAILED (payment processor rejects)
   COMPLETED → REFUND_PENDING → REFUNDED
4. Payment processing: simulate calling an external payment processor.
   The processor can succeed, fail, or timeout.
5. Retry logic: on timeout or transient failure, retry with exponential
   backoff (max 3 retries).
6. Double-entry bookkeeping: every payment creates two ledger entries —
   a debit on the payer's account and a credit on the payee's account.
   Ledger entries must always balance (sum of debits = sum of credits).
7. Account balances: derived from ledger entries.
8. Refunds: full or partial. Creates reverse ledger entries.
9. Webhook notifications: register callbacks for payment events
   (created, completed, failed, refunded).
10. Payment history: query payments by payer, payee, status, date range.
11. Currency support: amounts have a currency code. No cross-currency
    transfers (must match).

Interface
---------
class Payment:
    def __init__(self, payment_id: str, amount: float, currency: str,
                 payer_id: str, payee_id: str, status: str,
                 idempotency_key: str):
        """A payment."""

class LedgerEntry:
    def __init__(self, entry_id: str, account_id: str, amount: float,
                 currency: str, entry_type: str, reference_id: str,
                 timestamp: float):
        """A ledger entry. entry_type: 'DEBIT' or 'CREDIT'."""

class PaymentSystem:
    def __init__(self):
        """Initialize the payment system."""

    def create_account(self, account_id: str, currency: str = "USD",
                       initial_balance: float = 0) -> None:
        """Create an account with optional initial balance."""

    def process_payment(self, amount: float, currency: str,
                        payer_id: str, payee_id: str,
                        idempotency_key: str) -> Payment:
        """Process a payment. Returns the Payment with final status."""

    def refund(self, payment_id: str, amount: float = None) -> Payment:
        """Refund a payment (full if amount is None, partial otherwise)."""

    def get_payment(self, payment_id: str) -> Payment | None:
        """Look up a payment by ID."""

    def get_balance(self, account_id: str) -> float:
        """Get account balance derived from ledger."""

    def get_ledger(self, account_id: str) -> list[LedgerEntry]:
        """Get all ledger entries for an account."""

    def get_payments(self, account_id: str = None, status: str = None,
                     limit: int = 50) -> list[Payment]:
        """Query payments with filters."""

    def register_webhook(self, event: str, callback: callable) -> None:
        """Register a webhook callback for events:
        'payment.created', 'payment.completed', 'payment.failed',
        'payment.refunded'."""

    def set_processor(self, processor: callable) -> None:
        """Set the payment processor function. Signature:
        processor(amount, currency, payer, payee) -> {'status': 'success'|'failure'|'timeout'}"""

    def verify_ledger_integrity(self) -> bool:
        """Verify all debits equal all credits (double-entry invariant)."""

Example Usage
-------------
    ps = PaymentSystem()
    ps.create_account("alice", "USD", initial_balance=1000)
    ps.create_account("bob", "USD", initial_balance=0)

    # Process payment
    payment = ps.process_payment(100.0, "USD", "alice", "bob",
                                  idempotency_key="pay-001")
    assert payment.status == "COMPLETED"
    assert ps.get_balance("alice") == 900.0
    assert ps.get_balance("bob") == 100.0

    # Idempotent retry
    payment2 = ps.process_payment(100.0, "USD", "alice", "bob",
                                   idempotency_key="pay-001")
    assert payment2.payment_id == payment.payment_id  # same payment
    assert ps.get_balance("alice") == 900.0  # not charged again

    # Refund
    refund = ps.refund(payment.payment_id, amount=50.0)
    assert refund.status == "REFUNDED"
    assert ps.get_balance("alice") == 950.0
    assert ps.get_balance("bob") == 50.0

    # Ledger integrity
    assert ps.verify_ledger_integrity() == True

Constraints
-----------
- All amounts are positive floats with 2 decimal precision.
- Idempotency keys are unique strings.
- Payment IDs are auto-generated unique strings.
- Insufficient balance should fail the payment.
- Currency mismatch should fail the payment.
- Target: 200-400 lines of Python.

Testing Requirements
--------------------
1. Successful payment debits payer, credits payee.
2. Idempotency prevents double-charging.
3. Failed payment doesn't affect balances.
4. Retry logic handles transient failures.
5. Full and partial refunds work.
6. Refund exceeding payment amount fails.
7. Double-entry ledger always balances.
8. Insufficient balance rejects payment.
9. Currency mismatch rejects payment.
10. Webhook callbacks fire on status changes.
11. Payment history query works.
12. State machine transitions are valid.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. The key algorithmic choices:

- **Idempotency**: Simple dict lookup by key — O(1), no complexity needed
- **Double-entry**: Every money movement (payment, refund, initial balance) creates balanced debit+credit pairs against a SYSTEM contra-account
- **Retry**: Exponential backoff wrapping the injectable processor, max 3 attempts
- **Balances**: Derived from ledger (sum credits - sum debits), never stored directly
- **Partial refunds**: Track cumulative refunded amount on Payment to enforce refund ≤ original

[Committed changes to planner branch]