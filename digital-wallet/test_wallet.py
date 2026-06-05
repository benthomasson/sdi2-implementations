"""Tests for the digital wallet system."""

import threading
import pytest
from wallet import (
    WalletService, InsufficientFunds, DailyLimitExceeded,
    WalletFrozen, CurrencyMismatch, InvalidAmount, WalletNotFound
)


@pytest.fixture
def svc():
    s = WalletService()
    s.create_wallet("alice", "Alice", "USD", daily_limit=500)
    s.create_wallet("bob", "Bob", "USD", daily_limit=500)
    s.deposit("alice", 1000.0)
    return s


def test_example_from_spec():
    """Run the exact example from the task specification."""
    svc = WalletService()
    svc.create_wallet("alice", "Alice", "USD", daily_limit=500)
    svc.create_wallet("bob", "Bob", "USD", daily_limit=500)

    svc.deposit("alice", 1000.0)
    assert svc.get_balance("alice") == 1000.0

    debit, credit = svc.transfer("alice", "bob", 250.0)
    assert svc.get_balance("alice") == 750.0
    assert svc.get_balance("bob") == 250.0

    svc.transfer("alice", "bob", 200.0)
    assert svc.get_daily_spending("alice") == 450.0

    with pytest.raises(DailyLimitExceeded):
        svc.transfer("alice", "bob", 100.0)

    svc.freeze("bob")
    with pytest.raises(WalletFrozen):
        svc.withdraw("bob", 50.0)

    svc.unfreeze("bob")
    svc.withdraw("bob", 50.0)
    assert svc.get_balance("bob") == 400.0

    assert svc.verify_integrity()


def test_deposit_and_withdraw(svc):
    """Deposit increases balance, withdrawal decreases it."""
    svc.deposit("bob", 200.0)
    assert svc.get_balance("bob") == 200.0
    svc.withdraw("alice", 300.0)
    assert svc.get_balance("alice") == 700.0


def test_insufficient_funds(svc):
    """Insufficient funds rejected for both withdrawal and transfer."""
    with pytest.raises(InsufficientFunds):
        svc.withdraw("alice", 2000.0)
    with pytest.raises(InsufficientFunds):
        svc.transfer("alice", "bob", 2000.0)


def test_transfer_atomic(svc):
    """Transfer updates both balances atomically with correct tx types."""
    debit, credit = svc.transfer("alice", "bob", 250.0)
    assert svc.get_balance("alice") == 750.0
    assert svc.get_balance("bob") == 250.0
    assert debit.tx_type == "transfer_out"
    assert credit.tx_type == "transfer_in"
    assert debit.counterparty == "bob"
    assert credit.counterparty == "alice"


def test_daily_limit_enforcement(svc):
    """Daily limit blocks spending when exceeded."""
    svc.transfer("alice", "bob", 200.0)
    svc.withdraw("alice", 200.0)
    assert svc.get_daily_spending("alice") == 400.0
    with pytest.raises(DailyLimitExceeded):
        svc.withdraw("alice", 200.0)  # 600 > 500


def test_freeze_unfreeze(svc):
    """Frozen wallet blocks all ops; unfreeze restores access."""
    svc.freeze("alice")
    with pytest.raises(WalletFrozen):
        svc.deposit("alice", 100.0)
    with pytest.raises(WalletFrozen):
        svc.withdraw("alice", 100.0)
    with pytest.raises(WalletFrozen):
        svc.transfer("alice", "bob", 100.0)
    svc.unfreeze("alice")
    svc.withdraw("alice", 100.0)
    assert svc.get_balance("alice") == 900.0


def test_currency_mismatch():
    """Transfer between different currencies is rejected."""
    svc = WalletService()
    svc.create_wallet("usd", "A", "USD")
    svc.create_wallet("eur", "B", "EUR")
    svc.deposit("usd", 100.0)
    with pytest.raises(CurrencyMismatch):
        svc.transfer("usd", "eur", 50.0)


def test_negative_and_zero_amount_rejected(svc):
    """Negative and zero amounts are rejected."""
    with pytest.raises(InvalidAmount):
        svc.deposit("alice", -100.0)
    with pytest.raises(InvalidAmount):
        svc.withdraw("alice", 0)
    with pytest.raises(InvalidAmount):
        svc.transfer("alice", "bob", -25.0)


def test_audit_trail_and_transaction_history(svc):
    """Audit trail and transaction history are accurate."""
    svc.transfer("alice", "bob", 100.0)
    svc.withdraw("alice", 50.0)

    # Transaction history
    txs = svc.get_transactions("alice")
    assert len(txs) == 3  # deposit + transfer_out + withdrawal
    assert txs[0].tx_type == "deposit"
    assert txs[1].tx_type == "transfer_out"
    assert txs[2].tx_type == "withdrawal"
    assert svc.get_transactions("alice", tx_type="withdrawal") == [txs[2]]

    # Audit trail
    trail = svc.get_audit_trail("alice")
    assert len(trail) >= 3
    xfer = [e for e in trail if e["action"] == "transfer_out"][0]
    assert xfer["before_balance"] == 1000.0
    assert xfer["after_balance"] == 900.0


def test_concurrent_transfers_no_money_lost():
    """Concurrent transfers preserve total money in the system."""
    svc = WalletService()
    n_wallets = 10
    initial = 1000.0
    for i in range(n_wallets):
        svc.create_wallet(f"w{i}", f"Owner{i}", daily_limit=1_000_000)
        svc.deposit(f"w{i}", initial)
    total_before = sum(svc.get_balance(f"w{i}") for i in range(n_wallets))

    errors = []
    def do_transfers():
        import random
        for _ in range(100):
            a, b = random.sample(range(n_wallets), 2)
            try:
                svc.transfer(f"w{a}", f"w{b}", 1.0)
            except (InsufficientFunds, DailyLimitExceeded):
                pass
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=do_transfers) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors: {errors}"
    total_after = sum(svc.get_balance(f"w{i}") for i in range(n_wallets))
    assert abs(total_before - total_after) < 0.01
    assert svc.verify_integrity()


def test_integrity_after_many_ops(svc):
    """Integrity check passes after many operations."""
    for i in range(50):
        svc.transfer("alice", "bob", 5.0)
    svc.withdraw("bob", 100.0)
    assert svc.verify_integrity()
