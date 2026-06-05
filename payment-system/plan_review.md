# Plan Review: Payment System

## Plan Strengths

- Double-entry bookkeeping: every money movement (payment, refund, initial balance) creates balanced debit+credit pairs. Initial balances use a `__SYSTEM__` contra-account so the ledger always balances.
- Idempotency via key-to-payment-id map. Duplicate requests return the existing payment without side effects.
- Payment state machine: CREATED -> PROCESSING -> COMPLETED/FAILED, COMPLETED -> REFUND_PENDING -> REFUNDED. Refunds from REFUNDED state allow partial refunds after initial partial refund.
- Retry with exponential backoff: `base_delay * 2^attempt` on timeout, max 3 retries. Returns failure after exhausting retries.
- Partial refunds track cumulative `refunded_amount` on the payment. Validates `refunded_amount + refund_amount <= payment.amount`.
- Balance derived from ledger (sum credits - sum debits), not cached. Ensures consistency with ledger state.
- Webhook callbacks fire on each state transition. Errors in callbacks are caught and swallowed to prevent payment processing failure.

## Plan Gaps

1. **`time.sleep` in retry logic blocks the calling thread.** Line 154: `time.sleep(self._base_delay * (2 ** attempt))`. In a real system this would need async or a retry queue. The test sets `_base_delay = 0.01` to mitigate.

2. **Balance check before processor call creates a TOCTOU gap.** Between `get_balance` check (line 100) and ledger entry creation (line 129-138), another concurrent payment could drain the balance. No thread synchronization.

3. **Failed payments with idempotency keys are permanently failed.** If a payment fails due to a transient processor failure, the idempotency key maps to the FAILED payment. Retrying with the same key returns the FAILED result without re-processing.

4. **`get_balance` scans the entire ledger.** O(n) per balance query. A cached balance updated on each ledger entry would be O(1).

5. **Webhook exception swallowing.** Line 231: `except Exception: pass`. Silent failures in webhook delivery are hard to debug. Should at least log.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 238 lines. All 10 test cases pass including retry and ledger integrity verification.
