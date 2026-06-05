"""Payment processing system with idempotency, double-entry bookkeeping, and retry logic."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Payment:
    """A payment."""
    payment_id: str
    amount: float
    currency: str
    payer_id: str
    payee_id: str
    status: str
    idempotency_key: str
    created_at: float = field(default_factory=time.time)
    refunded_amount: float = 0.0


@dataclass
class LedgerEntry:
    """A ledger entry. entry_type: 'DEBIT' or 'CREDIT'."""
    entry_id: str
    account_id: str
    amount: float
    currency: str
    entry_type: str  # 'DEBIT' or 'CREDIT'
    reference_id: str
    timestamp: float = field(default_factory=time.time)


SYSTEM_ACCOUNT = "__SYSTEM__"


class PaymentSystem:
    """Payment system with idempotency, double-entry bookkeeping, and retry logic."""

    def __init__(self):
        self._accounts = {}  # account_id -> currency
        self._payments = {}  # payment_id -> Payment
        self._ledger = []  # list of LedgerEntry
        self._idempotency = {}  # idempotency_key -> payment_id
        self._webhooks = {}  # event -> [callbacks]
        self._processor = lambda amount, currency, payer, payee: {"status": "success"}
        self._max_retries = 3
        self._base_delay = 0.1

    def create_account(self, account_id, currency="USD", initial_balance=0):
        """Create an account with optional initial balance."""
        if account_id in self._accounts:
            raise ValueError(f"Account {account_id} already exists")
        self._accounts[account_id] = currency
        if initial_balance > 0:
            ref = f"initial-{account_id}"
            self._ledger.append(LedgerEntry(
                entry_id=str(uuid.uuid4()), account_id=account_id,
                amount=initial_balance, currency=currency,
                entry_type="CREDIT", reference_id=ref,
            ))
            self._ledger.append(LedgerEntry(
                entry_id=str(uuid.uuid4()), account_id=SYSTEM_ACCOUNT,
                amount=initial_balance, currency=currency,
                entry_type="DEBIT", reference_id=ref,
            ))

    def set_processor(self, processor):
        """Set the payment processor function.
        Args:
            processor: callable(amount, currency, payer, payee) -> {'status': 'success'|'failure'|'timeout'}
        """
        self._processor = processor

    def process_payment(self, amount, currency, payer_id, payee_id, idempotency_key):
        """Process a payment. Returns the Payment with final status."""
        # Idempotency check
        if idempotency_key in self._idempotency:
            return self._payments[self._idempotency[idempotency_key]]

        # Validate accounts
        if payer_id not in self._accounts:
            raise ValueError(f"Payer account {payer_id} not found")
        if payee_id not in self._accounts:
            raise ValueError(f"Payee account {payee_id} not found")

        # Currency check
        if self._accounts[payer_id] != currency or self._accounts[payee_id] != currency:
            payment = Payment(
                payment_id=str(uuid.uuid4()), amount=amount, currency=currency,
                payer_id=payer_id, payee_id=payee_id, status="FAILED",
                idempotency_key=idempotency_key,
            )
            self._payments[payment.payment_id] = payment
            self._idempotency[idempotency_key] = payment.payment_id
            self._fire_webhook("payment.failed", payment)
            return payment

        # Balance check
        if self.get_balance(payer_id) < amount:
            payment = Payment(
                payment_id=str(uuid.uuid4()), amount=amount, currency=currency,
                payer_id=payer_id, payee_id=payee_id, status="FAILED",
                idempotency_key=idempotency_key,
            )
            self._payments[payment.payment_id] = payment
            self._idempotency[idempotency_key] = payment.payment_id
            self._fire_webhook("payment.failed", payment)
            return payment

        # Create payment
        payment = Payment(
            payment_id=str(uuid.uuid4()), amount=amount, currency=currency,
            payer_id=payer_id, payee_id=payee_id, status="CREATED",
            idempotency_key=idempotency_key,
        )
        self._payments[payment.payment_id] = payment
        self._idempotency[idempotency_key] = payment.payment_id
        self._fire_webhook("payment.created", payment)

        # Transition to PROCESSING
        payment.status = "PROCESSING"

        # Call processor with retry
        result = self._call_processor_with_retry(amount, currency, payer_id, payee_id)

        if result["status"] == "success":
            # Create ledger entries
            self._ledger.append(LedgerEntry(
                entry_id=str(uuid.uuid4()), account_id=payer_id,
                amount=amount, currency=currency,
                entry_type="DEBIT", reference_id=payment.payment_id,
            ))
            self._ledger.append(LedgerEntry(
                entry_id=str(uuid.uuid4()), account_id=payee_id,
                amount=amount, currency=currency,
                entry_type="CREDIT", reference_id=payment.payment_id,
            ))
            payment.status = "COMPLETED"
            self._fire_webhook("payment.completed", payment)
        else:
            payment.status = "FAILED"
            self._fire_webhook("payment.failed", payment)

        return payment

    def _call_processor_with_retry(self, amount, currency, payer_id, payee_id):
        """Call processor with exponential backoff retry on timeout."""
        for attempt in range(self._max_retries):
            result = self._processor(amount, currency, payer_id, payee_id)
            if result["status"] != "timeout":
                return result
            if attempt < self._max_retries - 1:
                time.sleep(self._base_delay * (2 ** attempt))
        return {"status": "failure"}

    def refund(self, payment_id, amount=None):
        """Refund a payment (full if amount is None, partial otherwise)."""
        if payment_id not in self._payments:
            raise ValueError(f"Payment {payment_id} not found")
        payment = self._payments[payment_id]

        if payment.status not in ("COMPLETED", "REFUNDED"):
            raise ValueError(f"Cannot refund payment in {payment.status} state")

        refund_amount = amount if amount is not None else (payment.amount - payment.refunded_amount)
        if refund_amount <= 0:
            raise ValueError("Refund amount must be positive")
        if payment.refunded_amount + refund_amount > payment.amount:
            raise ValueError("Refund exceeds payment amount")

        payment.status = "REFUND_PENDING"

        # Create reverse ledger entries
        ref = f"refund-{payment_id}-{uuid.uuid4().hex[:8]}"
        self._ledger.append(LedgerEntry(
            entry_id=str(uuid.uuid4()), account_id=payment.payee_id,
            amount=refund_amount, currency=payment.currency,
            entry_type="DEBIT", reference_id=ref,
        ))
        self._ledger.append(LedgerEntry(
            entry_id=str(uuid.uuid4()), account_id=payment.payer_id,
            amount=refund_amount, currency=payment.currency,
            entry_type="CREDIT", reference_id=ref,
        ))

        payment.refunded_amount += refund_amount
        payment.status = "REFUNDED"
        self._fire_webhook("payment.refunded", payment)
        return payment

    def get_payment(self, payment_id):
        """Look up a payment by ID."""
        return self._payments.get(payment_id)

    def get_balance(self, account_id):
        """Get account balance derived from ledger."""
        balance = 0.0
        for entry in self._ledger:
            if entry.account_id == account_id:
                if entry.entry_type == "CREDIT":
                    balance += entry.amount
                else:
                    balance -= entry.amount
        return round(balance, 2)

    def get_ledger(self, account_id):
        """Get all ledger entries for an account."""
        return [e for e in self._ledger if e.account_id == account_id]

    def get_payments(self, account_id=None, status=None, limit=50):
        """Query payments with filters."""
        results = []
        for p in self._payments.values():
            if account_id and p.payer_id != account_id and p.payee_id != account_id:
                continue
            if status and p.status != status:
                continue
            results.append(p)
        return results[:limit]

    def register_webhook(self, event, callback):
        """Register a webhook callback for payment events."""
        self._webhooks.setdefault(event, []).append(callback)

    def _fire_webhook(self, event, payment):
        for cb in self._webhooks.get(event, []):
            try:
                cb(event, payment)
            except Exception:
                pass

    def verify_ledger_integrity(self):
        """Verify all debits equal all credits (double-entry invariant)."""
        total_debits = sum(e.amount for e in self._ledger if e.entry_type == "DEBIT")
        total_credits = sum(e.amount for e in self._ledger if e.entry_type == "CREDIT")
        return abs(total_debits - total_credits) < 0.001
