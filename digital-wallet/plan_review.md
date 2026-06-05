# Plan Review: Digital Wallet

## Plan Strengths

- Atomic transfers via lock ordering: `sorted([w_from, w_to], key=lambda w: w.wallet_id)` prevents deadlocks. Both locks held before any mutation.
- Optimistic locking with version counters on every wallet mutation.
- Balance rounding to 2 decimal places on every operation prevents float drift.
- `verify_integrity()` checks conservation law: `deposits - withdrawals == sum(balances)`.
- Audit trail records before/after balances for every state change including freeze/unfreeze.
- Transaction history filterable by type, with limit support.
- Concurrent transfer test with 10 wallets x 8 threads x 100 transfers validates thread safety.

## Plan Gaps

1. **`date.fromtimestamp()` and `date.today()` used local timezone.** Daily spending was computed using local-timezone date conversion, meaning the same UTC timestamp could fall on different dates depending on server timezone. **Fixed:** Changed to `datetime.fromtimestamp(ts, timezone.utc).date()` and `datetime.now(timezone.utc).date()`.

2. **`time.time()` used in Transaction `__post_init__` and `_record_audit`.** These make audit timestamps non-deterministic in tests. Not broken, but prevents testing timestamp-dependent behavior. The transfer method correctly overrides both transaction timestamps with the same `time.time()` value for atomicity.

3. **Daily spending scan is O(n) over all transactions.** `_get_daily_spending_internal` iterates every transaction to find matching wallet+date. For high-volume wallets this is slow. A per-wallet per-date spending cache would be O(1).

4. **No duplicate wallet ID check in `create_wallet`.** Creating a wallet with an existing ID silently overwrites it. Should raise an error.

## Implementation Issues (0 test failures)

No test failures. 3 timezone fixes applied (local -> UTC). Clean implementation at 243 lines.
