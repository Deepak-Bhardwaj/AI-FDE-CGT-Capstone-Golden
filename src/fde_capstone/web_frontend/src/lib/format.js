/** Shared presentation helpers. Status vocabulary is fixed so colour means one thing everywhere. */

const TONE_BY_STATUS = {
  PASS: 'pass',
  COMPLETE: 'pass',
  READY: 'pass',
  DELIVERED: 'pass',
  CONFIRMED: 'pass',
  APPROVED: 'pass',
  SUCCEEDED: 'pass',

  FAIL: 'fail',
  BLOCKED: 'fail',
  HALTED: 'fail',
  FAILED: 'fail',
  REJECTED: 'fail',
  DENIED: 'fail',
  CANCELLED: 'fail',

  UNKNOWN: 'unknown',
  NEEDS_EVIDENCE: 'unknown',
  WAITING: 'unknown',
  PENDING: 'unknown',
  AWAITING_APPROVAL: 'unknown',
  PROBABLE: 'unknown',

  CONFLICT: 'conflict',
  CONFLICTED: 'conflict',
  UNRESOLVED: 'conflict',
  COMPENSATED: 'conflict',
  UNTRUSTED: 'conflict',

  ACTIVE: 'info',
  IN_TRANSIT: 'info',

  NOT_APPLICABLE: 'neutral',
  NOT_STARTED: 'neutral',
  SKIPPED: 'neutral',
};

export function toneFor(status) {
  return TONE_BY_STATUS[String(status || '').toUpperCase()] || 'neutral';
}

/** Human-readable labels replace the raw enum names used by the API. */
const LABELS = {
  NOT_APPLICABLE: 'Not applicable',
  NEEDS_EVIDENCE: 'Needs evidence',
  NOT_STARTED: 'Not started',
  AWAITING_APPROVAL: 'Awaiting approval',
  APPROVED_AND_EXECUTED: 'Approved & executed',
  APPROVED_BUT_COMPENSATED: 'Approved, then compensated',
  IN_TRANSIT: 'In transit',
  QC_TESTING: 'QC testing',
  MFG_COMPLETE: 'Manufacturing complete',
  QA_HOLD: 'QA hold',
  IN_MANUFACTURING: 'In manufacturing',
  RETURN_TRANSIT: 'Return transit',
  INFUSION_READY: 'Infusion ready',
  APHERESIS_PENDING: 'Apheresis pending',
  QC_PENDING: 'QC pending',
  COI_INTEGRITY_QUERY: 'Chain-of-identity query',
  SLOT_CHANGE_REQUEST: 'Slot change request',
  ROUTE_UNCERTAINTY: 'Route uncertainty',
  SITE_READINESS_QUERY: 'Site readiness query',
  QA_EXCEPTION_NOTE: 'QA exception note',
  QC_DISCREPANCY: 'QC discrepancy',
  CUSTODY_DISCREPANCY: 'Custody discrepancy',
  UNKNOWN_SUBJECT: 'Unidentified subject',
  QA_REVIEW_SENSOR_INTEGRITY: 'QA review — sensor integrity',
  QA_REVIEW_EXCURSION_PROFILE: 'QA review — excursion profile',
  NO_EXCURSION_DETECTED: 'No excursion detected',
  CANNOT_DETERMINE: 'Cannot determine',
  BLOCK_RELEASE: 'Release blocked',
  ELIGIBLE_FOR_QA_REVIEW: 'Eligible for QA review',
  DO_NOT_MERGE: 'Do not merge',
  MERGE_CANDIDATE: 'Merge candidate',
  CORRESPONDENCE: 'Correspondence',
  QC_REPORT: 'QC report',
  COURIER_MANIFEST: 'Courier manifest',
  COI_EVIDENCE: 'Chain-of-identity evidence',
  SLOT_ORCHESTRATION_CONFLICT: 'Slot orchestration conflict',
};

export function label(value) {
  if (value === null || value === undefined || value === '') return '—';
  const key = String(value).toUpperCase();
  if (LABELS[key]) return LABELS[key];
  return String(value)
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());
}

export const REDACTED = '[redacted]';

export function isRedacted(value) {
  return value === REDACTED;
}

export function shortTime(iso) {
  if (!iso) return '—';
  return String(iso).slice(11, 16);
}

export function shortDate(iso) {
  if (!iso) return '—';
  return String(iso).slice(0, 10);
}

export function dateTime(iso) {
  if (!iso) return '—';
  return `${String(iso).slice(0, 10)} ${String(iso).slice(11, 16)}`;
}

export function percent(value, digits = 0) {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function hours(value) {
  if (value === null || value === undefined) return '—';
  return `${value}h`;
}
