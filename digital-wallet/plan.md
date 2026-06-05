# Plan (Iteration 1)

Task: Digital Wallet
===============
SDI Vol 2 Reference: Chapter 12 - Digital Wallet

Overview
--------
Build a digital wallet system with balance management, peer-to-peer transfers,
transaction history, daily limits, and audit trails. The core challenge is
ensuring transfer atomicity — if Alice sends $100 to Bob, Alice's balance must
decrease and Bob's must increase as a single atomic operation, even under
concurrent access. Uses techniques similar to database transactions.

Requirements
------------
1. Wallet creation: create wallets with a unique ID, owner name, and currency.
2. Deposits: add funds to a wallet from an external source.
3. Withdrawals: remove funds from a wallet (to external destination).
4. Transfers: move funds between two wallets atomically. Must prevent
   partial transfers (debit without credit or vice versa).
5. Balance inquiry: current balance derived from transaction history.
6. Transaction history: ordered log of all transactions with timestamps,
   type (deposit, withdrawal, transfer_in, transfer_out), amount,
   counterparty, and reference.
7. Daily limits: configurable daily spending limit per wallet. Transfers
   and withdrawals count toward the limit.
8. Concurrent safety: simulate concurrent transfers and verify no money
   is created or lost. Use optimistic locking (version numbers).
9. Multi-currency: wallets have a currency. Transfers between same-currency
   wallets only (no FX).
10. Audit trail: every state change is logged with before/after balances
    and a reason.
11. Freeze/unfreeze: suspend a wallet to prevent transactions.

Interface
---------
class Wallet:
    def __init__(self, wallet_id: str, owner: str, currency: str = "USD"):
        """A digital wallet."""

class Transaction:
    def __init__(self, tx_id: str, wallet_id: str, tx_type: str,
                 amount: float, balance_after: float, counterparty: str = None,
                 reference: str = None, timestamp: float = None):
        """A transaction record."""

class WalletService:
    def __init__(self):
        """Initialize the wallet service."""

    def create_wallet(self, wallet_id: str, owner: str,
                      currency: str = "USD",
                      daily_limit: float = 10000.0) -> Wallet:
        """Create a new wallet."""

    def deposit(self, wallet_id: str, amount: float,
                reference: str = None) -> Transaction:
        """Deposit funds into a wallet."""

    def withdraw(self, wallet_id: str, amount: float,
                 reference: str = None) -> Transaction:
        """Withdraw funds. Raises InsufficientFunds if balance too low.
        Raises DailyLimitExceeded if limit would be exceeded."""

    def transfer(self, from_wallet: str, to_wallet: str, amount: float,
                 reference: str = None) -> tuple[Transaction, Transaction]:
        """Transfer funds atomically. Returns (debit_tx, credit_tx)."""

    def get_balance(self, wallet_id: str) -> float:
        """Get current balance."""

    def get_transactions(self, wallet_id: str, limit: int = 50,
                         tx_type: str = None) -> list[Transaction]:
        """Get transaction history, optionally filtered by type."""

    def get_daily_spending(self, wallet_id: str, date: str = None) -> float:
        """Get total spending (transfers out + withdrawals) for a date."""

    def set_daily_limit(self, wallet_id: str, limit: float) -> None:
        """Update daily spending limit."""

    def freeze(self, wallet_id: str) -> None:
        """Freeze wallet — all transactions blocked."""

    def unfreeze(self, wallet_id: str) -> None:
        """Unfreeze wallet."""

    def get_audit_trail(self, wallet_id: str) -> list[dict]:
        """Get audit trail: [{action, before_balance, after_balance,
        amount, timestamp, reason}]."""

    def verify_integrity(self) -> bool:
        """Verify no money created or destroyed: sum of all deposits =
        sum of all balances + sum of all withdrawals."""

Example Usage
-------------
    svc = WalletService()
    svc.create_wallet("alice", "Alice", "USD", daily_limit=500)
    svc.create_wallet("bob", "Bob", "USD", daily_limit=500)

    svc.deposit("alice", 1000.0)
    assert svc.get_balance("alice") == 1000.0

    # Transfer
    debit, credit = svc.transfer("alice", "bob", 250.0)
    assert svc.get_balance("alice") == 750.0
    assert svc.get_balance("bob") == 250.0

    # Daily limit
    svc.transfer("alice", "bob", 200.0)
    assert svc.get_daily_spending("alice") == 450.0

    # This should fail (would exceed 500 limit)
    try:
        svc.transfer("alice", "bob", 100.0)
    except Exception:
        pass  # DailyLimitExceeded

    # Freeze
    svc.freeze("bob")
    try:
        svc.withdraw("bob", 50.0)
    except Exception:
        pass  # WalletFrozen

    svc.unfreeze("bob")
    svc.withdraw("bob", 50.0)
    assert svc.get_balance("bob") == 400.0

    # Integrity
    assert svc.verify_integrity() == True

Constraints
-----------
- Amounts are positive floats, 2 decimal precision.
- Transfers are atomic (all or nothing).
- Daily limits reset at midnight (date-based).
- Currency mismatch between wallets rejects transfer.
- Handle up to 10,000 wallets and 1,000,000 transactions.
- Target: 200-350 lines of Python.

Testing Requirements
--------------------
1. Deposit increases balance.
2. Withdrawal decreases balance.
3. Insufficient funds rejects withdrawal/transfer.
4. Transfer is atomic: both balances change.
5. Daily limit enforcement.
6. Freeze blocks all transactions.
7. Transaction history is ordered and accurate.
8. Concurrent transfers don't create/lose money.
9. Currency mismatch rejected.
10. Audit trail records all changes.
11. Integrity check passes after many operations.
12. Negative amounts rejected.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `/Users/ben/git/sdi2-results/workspaces/digital-wallet/planner/PLAN.md`.

**Summary:** Single-module Python implementation with optimistic locking (version counters) + per-wallet `threading.Lock` with lock ordering for deadlock prevention. Transfers are atomic by holding both locks before any mutation. Balance cached on wallet but verifiable against transaction history. All 11 requirements map directly to methods on the provided `WalletService` interface — no extra abstraction needed.

[Committed changes to planner branch]