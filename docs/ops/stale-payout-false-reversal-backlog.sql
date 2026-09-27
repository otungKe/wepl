-- ============================================================================
-- Backlog check: did the stale-payout sweep ever falsely reverse a settled
-- payout, before PR #217 stopped it?
--
-- Paste into the Neon SQL editor. Run against STAGING, then PRODUCTION.
-- Strictly READ-ONLY: no INSERT/UPDATE/DELETE, no DDL, no locks taken.
--
-- Why this exists
-- ---------------
-- Until PR #217 (merged 2026-09-26), `recover_stale_processing_transactions`
-- (backend/apps/payments/payouts.py) force-failed any payout still PROCESSING
-- after 60 minutes and wrote a reversal. It asked the rail first, but Daraja's
-- TransactionStatusQuery answers asynchronously, so `request_payout_result`
-- always reports `unknown` — and `unknown` was treated the same as a confirmed
-- failure. If Safaricom had actually paid and the callback was lost or slow, the
-- ledger was credited back for money that had left the float. `FAILED` is
-- terminal, so the late success callback could not correct it: `B2CResultView`
-- catches the `TransitionError`, logs a warning and returns 200.
--
-- #217 fixed the behaviour — an inconclusive rail now leaves the payout in
-- PROCESSING for the FinOps desk (see the "Not addressed" note in
-- docs/adr/0032-payout-orchestration-in-payments.md). It does not undo anything
-- the old code already wrote, which is what this script looks for.
--
-- Q1-Q3 filter on `failure_reason LIKE 'Auto-recovered after 60 min%'` — the
-- exact wording the OLD code wrote. Rows written since #217 read "Rail confirmed
-- failure after 60 min" and are legitimate, because the rail said so. Do not
-- widen the filter to catch them.
--
-- Run all five. Q0 first: it tells you whether a zero result below means "clean"
-- or "no payouts to have been wrong about".
-- ============================================================================


-- ── Q0. Denominator: is there any payout history at all? ────────────────────
SELECT
    COUNT(*)                                         AS payout_intents_total,
    COUNT(*) FILTER (WHERE status = 'succeeded')     AS succeeded,
    COUNT(*) FILTER (WHERE status = 'failed')        AS failed,
    COUNT(*) FILTER (WHERE status = 'pending')       AS still_pending,
    MIN(created_at)                                  AS first_seen,
    MAX(created_at)                                  AS last_seen
FROM payments_paymentintent
WHERE direction = 'payout';


-- ── Q1. Did the old auto-recovery ever fire? ───────────────────────────────
-- Every row is a payout the sweep declared failed and reversed on its own. Not
-- all are wrong — but none were confirmed failed by the rail.
SELECT
    COUNT(*)                 AS force_failed_by_sweep,
    COALESCE(SUM(amount), 0) AS total_amount,
    MIN(updated_at)          AS first_occurrence,
    MAX(updated_at)          AS last_occurrence
FROM ledger_financialtransaction
WHERE state = 'FAILED'
  AND failure_reason LIKE 'Auto-recovered after 60 min%';


-- ── Q2. THE SMOKING GUN ────────────────────────────────────────────────────
-- Force-failed and reversed by the sweep, but the payment rail says the payout
-- SUCCEEDED. Each row is money that left the float while the ledger was credited
-- back for it.
--
-- This is visible because `B2CResultView` resolves the `PaymentIntent` *before*
-- it touches the `FinancialTransaction`, in its own try/except. So a late success
-- callback still marked the intent succeeded even though the FT transition raised
-- `TransitionError` and was abandoned.
--
-- ANY ROW HERE IS A CONFIRMED FALSE REVERSAL.
SELECT
    ft.id                                        AS ft_id,
    'WEPL-TXN-' || LPAD(ft.id::text, 6, '0')     AS reference,
    ft.op_type,
    ft.amount,
    ft.context_type,
    ft.context_id,
    ft.recipient_phone,
    ft.updated_at                                AS ft_force_failed_at,
    pi.provider_ref,
    pi.status                                    AS intent_status,
    pi.receipt                                   AS rail_receipt,
    pi.callback_received_at,
    pi.provider_completed_at,
    pi.provider_completed_at - ft.updated_at     AS callback_arrived_after_reversal_by
FROM ledger_financialtransaction ft
JOIN payments_paymentintent pi
     ON pi.financial_transaction_id = ft.id
WHERE ft.state = 'FAILED'
  AND ft.failure_reason LIKE 'Auto-recovered after 60 min%'
  AND pi.status = 'succeeded'
ORDER BY ft.updated_at DESC;


-- ── Q3. Wider net: a success result landed in the raw callback log ─────────
-- Catches the same defect when the `PaymentIntent` was not updated either (its
-- resolve is best-effort and can itself have failed). Reads the raw Daraja
-- payload: `ResultCode` 0 means Safaricom paid.
SELECT
    ft.id                                    AS ft_id,
    'WEPL-TXN-' || LPAD(ft.id::text, 6, '0') AS reference,
    ft.amount,
    ft.state                                 AS ft_state,
    ft.updated_at                            AS ft_force_failed_at,
    pe.received_at                           AS success_callback_received_at,
    pe.provider_ref,
    pe.payload #>> '{Result,ResultCode}'     AS result_code,
    pe.payload #>> '{Result,ResultDesc}'     AS result_desc
FROM ledger_financialtransaction ft
JOIN payments_paymentintent pi
     ON pi.financial_transaction_id = ft.id
JOIN payments_providerevent pe
     ON pe.payment_intent_id = pi.id
WHERE ft.state = 'FAILED'
  AND ft.failure_reason LIKE 'Auto-recovered after 60 min%'
  AND pe.event_type = 'payout_result'
  AND (pe.payload #>> '{Result,ResultCode}') = '0'
ORDER BY pe.received_at DESC;


-- ── Q4. The live FinOps queue ──────────────────────────────────────────────
-- Since #217 these are parked rather than reversed, so this is the work sitting
-- on the desk: funds reserved, awaiting a `confirm_paid` or `mark_failed`.
SELECT
    ft.id                                    AS ft_id,
    'WEPL-TXN-' || LPAD(ft.id::text, 6, '0') AS reference,
    ft.op_type,
    ft.amount,
    ft.updated_at,
    NOW() - ft.updated_at                    AS stuck_for,
    pi.provider_ref,
    pi.status                                AS intent_status
FROM ledger_financialtransaction ft
LEFT JOIN payments_paymentintent pi
     ON pi.financial_transaction_id = ft.id
WHERE ft.state = 'PROCESSING'
  AND ft.updated_at < NOW() - INTERVAL '60 minutes'
ORDER BY ft.updated_at;


-- ============================================================================
-- Reading the results
--
--   Q0 zero            → no payout history; Q1-Q4 being empty proves nothing.
--   Q1 zero            → the old auto-recovery never fired. Clean, nothing owed.
--   Q1 > 0, Q2/Q3 zero → it fired, but no evidence any of those payouts actually
--                        settled. Note Q2/Q3 can only see it where a late
--                        callback arrived at all: a callback that never came
--                        leaves no trace either way, so this is "no evidence of
--                        harm", not "no harm".
--   Q2 or Q3 non-zero  → confirmed false reversals, and they are still in the
--                        books. Each needs a correcting journal posted through
--                        `post_journal` (never an `AccountBalance` patch —
--                        ADR-0002), and a check of whether the domain object was
--                        re-triggered and the member paid twice.
-- ============================================================================
