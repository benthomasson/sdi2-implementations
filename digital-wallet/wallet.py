"""Digital wallet system with atomic transfers, daily limits, and audit trails."""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


# Exceptions
class InsufficientFunds(Exception): pass
class DailyLimitExceeded(Exception): pass
class WalletFrozen(Exception): pass
class CurrencyMismatch(Exception): pass
class ConcurrencyError(Exception): pass
class WalletNotFound(Exception): pass
class InvalidAmount(Exception): pass


@dataclass
class Wallet:
    """A digital wallet."""
    wallet_id: str
    owner: str
    currency: str = "USD"
    daily_limit: float = 10000.0
    frozen: bool = False
    balance: float = 0.0
    version: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class Transaction:
    """A transaction record."""
    tx_id: str
    wallet_id: str
    tx_type: str
    amount: float
    balance_after: float
    counterparty: str = None
    reference: str = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class AuditEntry:
    action: str
    wallet_id: str
    before_balance: float
    after_balance: float
    amount: float
    timestamp: float
    reason: str


class WalletService:
    """Manages wallets with atomic transfers and audit logging."""

    def __init__(self):
        self.wallets: dict[str, Wallet] = {}
        self.transactions: list[Transaction] = []
        self.audit_trail: list[AuditEntry] = []
        self._tx_lock = threading.Lock()

    def _get_wallet(self, wallet_id: str) -> Wallet:
        if wallet_id not in self.wallets:
            raise WalletNotFound(f"Wallet '{wallet_id}' not found")
        return self.wallets[wallet_id]

    def _check_frozen(self, wallet: Wallet):
        if wallet.frozen:
            raise WalletFrozen(f"Wallet '{wallet.wallet_id}' is frozen")

    def _validate_amount(self, amount: float):
        if amount <= 0:
            raise InvalidAmount("Amount must be positive")

    def _get_daily_spending_internal(self, wallet_id: str, target_date: str) -> float:
        total = 0.0
        for tx in self.transactions:
            if tx.wallet_id == wallet_id and tx.tx_type in ("withdrawal", "transfer_out"):
                tx_date = datetime.fromtimestamp(tx.timestamp, timezone.utc).date().isoformat()
                if tx_date == target_date:
                    total += tx.amount
        return round(total, 2)

    def _record_audit(self, action, wallet_id, before, after, amount, reason):
        self.audit_trail.append(AuditEntry(
            action=action, wallet_id=wallet_id, before_balance=before,
            after_balance=after, amount=amount, timestamp=time.time(), reason=reason
        ))

    def _make_tx_id(self) -> str:
        return str(uuid.uuid4())

    def create_wallet(self, wallet_id: str, owner: str, currency: str = "USD",
                      daily_limit: float = 10000.0) -> Wallet:
        """Create a new wallet."""
        w = Wallet(wallet_id=wallet_id, owner=owner, currency=currency, daily_limit=daily_limit)
        self.wallets[wallet_id] = w
        self._record_audit("create", wallet_id, 0.0, 0.0, 0.0, f"Wallet created for {owner}")
        return w

    def deposit(self, wallet_id: str, amount: float, reference: str = None) -> Transaction:
        """Deposit funds into a wallet."""
        self._validate_amount(amount)
        amount = round(amount, 2)
        w = self._get_wallet(wallet_id)
        with w._lock:
            self._check_frozen(w)
            before = w.balance
            w.balance = round(w.balance + amount, 2)
            w.version += 1
            tx = Transaction(self._make_tx_id(), wallet_id, "deposit", amount, w.balance, reference=reference)
            with self._tx_lock:
                self.transactions.append(tx)
            self._record_audit("deposit", wallet_id, before, w.balance, amount,
                               reference or "Deposit")
            return tx

    def withdraw(self, wallet_id: str, amount: float, reference: str = None) -> Transaction:
        """Withdraw funds from a wallet."""
        self._validate_amount(amount)
        amount = round(amount, 2)
        w = self._get_wallet(wallet_id)
        with w._lock:
            self._check_frozen(w)
            if w.balance < amount:
                raise InsufficientFunds(f"Balance {w.balance} < {amount}")
            today = datetime.now(timezone.utc).date().isoformat()
            spent = self._get_daily_spending_internal(wallet_id, today)
            if spent + amount > w.daily_limit:
                raise DailyLimitExceeded(f"Would exceed daily limit of {w.daily_limit}")
            before = w.balance
            w.balance = round(w.balance - amount, 2)
            w.version += 1
            tx = Transaction(self._make_tx_id(), wallet_id, "withdrawal", amount, w.balance, reference=reference)
            with self._tx_lock:
                self.transactions.append(tx)
            self._record_audit("withdrawal", wallet_id, before, w.balance, amount,
                               reference or "Withdrawal")
            return tx

    def transfer(self, from_wallet: str, to_wallet: str, amount: float,
                 reference: str = None) -> tuple:
        """Transfer funds atomically between two wallets."""
        self._validate_amount(amount)
        amount = round(amount, 2)
        w_from = self._get_wallet(from_wallet)
        w_to = self._get_wallet(to_wallet)
        if w_from.currency != w_to.currency:
            raise CurrencyMismatch(f"{w_from.currency} != {w_to.currency}")
        # Lock ordering by wallet_id to prevent deadlocks
        locks = sorted([w_from, w_to], key=lambda w: w.wallet_id)
        with locks[0]._lock:
            with locks[1]._lock:
                self._check_frozen(w_from)
                self._check_frozen(w_to)
                if w_from.balance < amount:
                    raise InsufficientFunds(f"Balance {w_from.balance} < {amount}")
                today = datetime.now(timezone.utc).date().isoformat()
                spent = self._get_daily_spending_internal(from_wallet, today)
                if spent + amount > w_from.daily_limit:
                    raise DailyLimitExceeded(f"Would exceed daily limit of {w_from.daily_limit}")
                before_from = w_from.balance
                before_to = w_to.balance
                w_from.balance = round(w_from.balance - amount, 2)
                w_to.balance = round(w_to.balance + amount, 2)
                w_from.version += 1
                w_to.version += 1
                debit = Transaction(self._make_tx_id(), from_wallet, "transfer_out", amount,
                                    w_from.balance, counterparty=to_wallet, reference=reference)
                credit = Transaction(self._make_tx_id(), to_wallet, "transfer_in", amount,
                                     w_to.balance, counterparty=from_wallet, reference=reference)
                now = time.time()
                debit.timestamp = now
                credit.timestamp = now
                with self._tx_lock:
                    self.transactions.append(debit)
                    self.transactions.append(credit)
                self._record_audit("transfer_out", from_wallet, before_from, w_from.balance,
                                   amount, reference or f"Transfer to {to_wallet}")
                self._record_audit("transfer_in", to_wallet, before_to, w_to.balance,
                                   amount, reference or f"Transfer from {from_wallet}")
                return (debit, credit)

    def get_balance(self, wallet_id: str) -> float:
        """Get current balance."""
        return self._get_wallet(wallet_id).balance

    def get_transactions(self, wallet_id: str, limit: int = 50,
                         tx_type: str = None) -> list:
        """Get transaction history, optionally filtered by type."""
        result = [t for t in self.transactions if t.wallet_id == wallet_id]
        if tx_type:
            result = [t for t in result if t.tx_type == tx_type]
        return result[-limit:]

    def get_daily_spending(self, wallet_id: str, target_date: str = None) -> float:
        """Get total spending for a date (default: today)."""
        self._get_wallet(wallet_id)
        if target_date is None:
            target_date = datetime.now(timezone.utc).date().isoformat()
        return self._get_daily_spending_internal(wallet_id, target_date)

    def set_daily_limit(self, wallet_id: str, limit: float) -> None:
        """Update daily spending limit."""
        w = self._get_wallet(wallet_id)
        w.daily_limit = limit

    def freeze(self, wallet_id: str) -> None:
        """Freeze wallet."""
        w = self._get_wallet(wallet_id)
        w.frozen = True
        self._record_audit("freeze", wallet_id, w.balance, w.balance, 0.0, "Wallet frozen")

    def unfreeze(self, wallet_id: str) -> None:
        """Unfreeze wallet."""
        w = self._get_wallet(wallet_id)
        w.frozen = False
        self._record_audit("unfreeze", wallet_id, w.balance, w.balance, 0.0, "Wallet unfrozen")

    def get_audit_trail(self, wallet_id: str) -> list:
        """Get audit trail for a wallet."""
        return [
            {"action": a.action, "before_balance": a.before_balance,
             "after_balance": a.after_balance, "amount": a.amount,
             "timestamp": a.timestamp, "reason": a.reason}
            for a in self.audit_trail if a.wallet_id == wallet_id
        ]

    def verify_integrity(self) -> bool:
        """Verify no money created or destroyed."""
        total_deposits = sum(t.amount for t in self.transactions if t.tx_type == "deposit")
        total_withdrawals = sum(t.amount for t in self.transactions if t.tx_type == "withdrawal")
        total_balances = sum(w.balance for w in self.wallets.values())
        return abs(total_deposits - total_withdrawals - total_balances) < 0.01
