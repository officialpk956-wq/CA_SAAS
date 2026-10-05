// Same-origin proxy to the API (see next.config.ts); the session cookie travels automatically.
const API_BASE_URL = '/api';


export interface Client {
  id: string;
  name: string;
  created_at: string;
  contact_email?: string | null;
  contact_phone?: string | null;
}

export interface Registration {
  id: string;
  client_id: string;
  gstin: string;
  legal_name: string;
  created_at: string;
}

export interface Period {
  id: string;
  registration_id: string;
  period_code: string;
  status: string;
  created_at: string;
}

export interface ImportBatch {
  id: string;
  period_id: string;
  source_type: 'purchase' | 'statement';  // backend values
  status: string;  // 'preview' | 'committed'
  original_filename?: string;
  record_count: number;
  invalid_count: number;
  commit_note?: string | null;
  created_at: string;
}

export interface ReconciliationRun {
  id: string;           // backend field name
  period_id: string;
  purchase_batch_id: string;
  statement_batch_id: string;
  status: string;
  created_at: string;
  error_message?: string;
  summary_data: {
    distinct_results_by_status: Record<string, number>;
    matched_pair_count: number;
    purchase_rows_total: number;
    statement_rows_total: number;
  };
  results?: ReconciliationResult[];
}

export interface ReconciliationResult {
  id: string;
  result_id: string;
  status: string;
  reason: string;
  purchase_record_ids: string[];
  statement_record_ids: string[];
  review_status: string;
  differences: Record<string, string>;
  purchase_records: SourceRecord[];
  statement_records: SourceRecord[];
  history: ReviewEvent[];
}

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(`API Error: ${status} - ${JSON.stringify(data)}`);
  }
}

async function fetchApi(path: string, options: RequestInit = {}) {
  const url = `${API_BASE_URL}${path}`;
  const headers = {

    ...(options.headers || {}),
  };

  const response = await fetch(url, { ...options, headers });
  
  if (response.status === 401 && typeof window !== 'undefined' && !path.startsWith('/auth/')) {
    // Session missing or expired: full page load to the login page (drops in-memory state), then back here.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }
  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = "Request failed";
    }
    throw new ApiError(response.status, errorData);
  }

  // Handle empty responses or binary responses (like Excel export)
  if (response.status === 204) return null;
  
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  
  if (contentType && contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
    return response.blob();
  }

  return response.text();
}

export const api = {
  getSalesImports: (periodId: string): Promise<SalesBatch[]> => fetchApi(`/periods/${periodId}/sales-imports`),
  uploadSales: (periodId: string, file: File): Promise<SalesBatch> => { const form = new FormData(); form.append('file', file); return fetchApi(`/periods/${periodId}/sales-imports`, { method: 'POST', body: form }); },
  getSales: (batchId: string, offset = 0, status = 'all'): Promise<SalesDetail> => fetchApi(`/sales-imports/${batchId}?offset=${offset}&status=${status}`),
  commitSales: (batchId: string, acknowledge_blocked: boolean, note: string) => fetchApi(`/sales-imports/${batchId}/commit`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acknowledge_blocked, note }) }),
  reviewSales: (batchId: string, recordId: string, data: { decision: string; note: string; previous_review_id: string | null }) => fetchApi(`/sales-imports/${batchId}/rows/${recordId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  exportSales: (batchId: string): Promise<Blob> => fetchApi(`/sales-imports/${batchId}/export`),
  salesTemplate: (version: '1' | '2' = '1'): Promise<string> => fetchApi(`/sales/template?version=${version}`),
  gstr1Draft: (batchId: string): Promise<{ document: { fp: string } & Record<string, unknown>; warnings: string[]; included_rows: number; notice: string }> => fetchApi(`/sales-imports/${batchId}/gstr1`),
  // Clients
  getClients: () => fetchApi('/clients'),
  createClient: (data: { name: string }) => fetchApi('/clients', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),

  // Registrations
  getRegistrations: (clientId: string) => fetchApi(`/clients/${clientId}/registrations`),
  createRegistration: (clientId: string, data: { gstin: string, legal_name: string }) => 
    fetchApi(`/clients/${clientId}/registrations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Periods
  getPeriods: (registrationId: string) => fetchApi(`/registrations/${registrationId}/periods`),
  createPeriod: (registrationId: string, periodCode: string) => 
    fetchApi(`/registrations/${registrationId}/periods`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ period_code: periodCode }),
    }),
  getPeriod: (periodId: string) => fetchApi(`/periods/${periodId}`),

  getCategories: (periodId: string, batchId: string, offset = 0): Promise<CategoryPage> => fetchApi(`/periods/${periodId}/categories?batch_id=${batchId}&offset=${offset}`),
  suggestCategory: (recordId: string): Promise<CategoryProposal> => fetchApi(`/records/${recordId}/category-suggestion`, { method: 'POST' }),
  decideCategory: (recordId: string, data: CategoryDecisionInput) => fetchApi(`/records/${recordId}/category-decisions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  deactivateCategoryRule: (id: string) => fetchApi(`/category-rules/${id}/deactivate`, { method: 'POST' }),
  // Imports
  uploadImport: (periodId: string, type: 'purchase_register' | 'statement_2b', file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    // Map frontend type names to backend source_type values
    const sourceType = type === 'purchase_register' ? 'purchase' : 'statement';
    return fetchApi(`/periods/${periodId}/imports?source_type=${sourceType}`, {
      method: 'POST',
      body: formData,
    });
  },
  importGstr2b: (periodId: string, file: File): Promise<{ batch: ImportBatch; conversion: Gstr2bConversion }> => { const form = new FormData(); form.append('file', file); return fetchApi(`/periods/${periodId}/imports/gstr2b`, { method: 'POST', body: form }); },
  getImportRows: (batchId: string, offset = 0): Promise<{ total: number; items: SourceRecord[] }> => fetchApi(`/imports/${batchId}/rows?offset=${offset}&limit=25`),
  getRuns: (periodId: string): Promise<ReconciliationRun[]> => fetchApi(`/periods/${periodId}/reconciliation-runs`),
  getImports: (periodId: string) => fetchApi(`/periods/${periodId}/imports`),
  commitImport: (batchId: string, acknowledgeInvalid: boolean, note: string) => 
    fetchApi(`/imports/${batchId}/commit?acknowledge_invalid=${acknowledgeInvalid}&note=${encodeURIComponent(note)}`, {
      method: 'POST',
    }),

  // Reconciliation
  runReconciliation: (periodId: string, purchaseBatchId: string, statementBatchId: string) => 
    fetchApi(`/periods/${periodId}/reconciliation-runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ purchase_batch_id: purchaseBatchId, statement_batch_id: statementBatchId }),
    }),
  getReconciliationRun: (periodId: string, runId: string) => 
    fetchApi(`/periods/${periodId}/reconciliation-runs/${runId}`),
  getReconciliationResults: (periodId: string, runId: string) =>
    fetchApi(`/periods/${periodId}/reconciliation-runs/${runId}/results`),

  // Export
  exportReconciliation: (periodId: string, runId: string) => 
    fetchApi(`/periods/${periodId}/reconciliation-runs/${runId}/export`),
    
  // Resolutions
  resolveException: (runId: string, resultId: string, data: { decision: string, notes: string }) =>
    fetchApi(`/runs/${runId}/results/${resultId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision: data.decision, note: data.notes }), // backend uses 'note' singular
    }),
};

export interface SourceRecord { record_id: string; row_number: number; is_valid: boolean; raw_data: Record<string, string>; issues: string[] }
export interface ReviewEvent { id: string; decision: string; note: string; actor_id: string; created_at: string }
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const data = error.data as { detail?: unknown };
    return typeof data?.detail === 'string' ? data.detail : 'Please check the supplied fields and try again.';
  }
  return 'Unable to reach the API. Check the local backend and retry.';
}

export interface CategoryProposal { id: string; source: string; model_version: string; category: string | null; evidence: string | null; status: string }
export interface CategoryHistory { id: string; category: string | null; action: string; note: string; actor_id: string; created_at: string }
export interface CategoryRow { id: string; record_id: string; supplier_ref: string; description: string; invoice_date: string; category: string | null; last_decision_id: string | null; proposal: CategoryProposal | null; history: CategoryHistory[] }
export interface CategoryRule { id: string; supplier_ref: string; description: string; category: string; effective_from: string; active: boolean }
export interface CategoryPage { categories: string[]; total: number; items: CategoryRow[]; rules: CategoryRule[]; mode: string }
export interface CategoryDecisionInput { action: 'accept' | 'reject' | 'manual'; category?: string; proposal_id?: string; previous_decision_id: string | null; note: string; save_rule: boolean; effective_from?: string }

export interface SalesBatch { id: string; period_id: string; user_id: string; filename: string; file_hash: string; contract_version: string; status: string; commit_note: string | null; created_at: string }
export interface SalesReview { id: string; actor_id: string; decision: string; note: string; created_at: string }
export interface SalesRow { id: string; row_number: number; raw_data: Record<string,string>; validation_status: string; issues: string[]; decision: string; previous_review_id: string | null; history: SalesReview[] }
export interface SalesSummary { source_rows: number; ready: number; invalid: number; duplicate: number; unsupported: number; included: number; excluded: number; pending: number; included_totals: Record<string,string> }
export interface SalesDetail { batch: SalesBatch; summary: SalesSummary; items: SalesRow[]; total: number }

// Phase 5A: tax worksheet, approvals and audit history
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const worksheetApi = {
  itcDecisions: (runId: string): Promise<ItcResult[]> => fetchApi(`/runs/${runId}/itc-decisions`),
  decideItc: (runId: string, items: { result_id: string; decision: string; previous_decision_id: string | null }[], note: string) => fetchApi(`/runs/${runId}/itc-decisions`, json('POST', { items, note })),
  adjustments: (periodId: string): Promise<TaxAdjustment[]> => fetchApi(`/periods/${periodId}/adjustments`),
  addAdjustment: (periodId: string, data: { adjustment_type: string; tax_head: string; amount: string; note: string }) => fetchApi(`/periods/${periodId}/adjustments`, json('POST', data)),
  voidAdjustment: (id: string, reason: string) => fetchApi(`/adjustments/${id}/void`, json('POST', { reason })),
  preview: (periodId: string, salesBatchId: string, runId: string): Promise<WorksheetPreview> => fetchApi(`/periods/${periodId}/worksheet?sales_batch_id=${salesBatchId}&run_id=${runId}`),
  drafts: (periodId: string): Promise<TaxDraft[]> => fetchApi(`/periods/${periodId}/tax-drafts`),
  createDraft: (periodId: string, sales_batch_id: string, run_id: string): Promise<TaxDraft> => fetchApi(`/periods/${periodId}/tax-drafts`, json('POST', { sales_batch_id, run_id })),
  approve: (draftId: string, note: string) => fetchApi(`/tax-drafts/${draftId}/approve`, json('POST', { note })),
  reopen: (approvalId: string, reason: string) => fetchApi(`/tax-approvals/${approvalId}/reopen`, json('POST', { reason })),
  filingEvidence: (approvalId: string, data: { arn: string; filed_on: string; note: string }) => fetchApi(`/tax-approvals/${approvalId}/filing-evidence`, json('POST', data)),
  exportDraft: (draftId: string): Promise<Blob> => fetchApi(`/tax-drafts/${draftId}/export`),
  auditEvents: (periodId?: string): Promise<AuditEntry[]> => fetchApi(`/audit-events?limit=200${periodId ? `&period_id=${periodId}` : ''}`),
};
export interface ItcResult { result_id: string; status: string; reason: string; purchase_record_ids: string[]; itc_at_stake: string | null; statement_record_ids: string[]; decision: string; previous_decision_id: string | null; history: ReviewEvent[] }
export interface TaxAdjustment { id: string; adjustment_type: string; tax_head: string; amount: string; note: string; actor_id: string; created_at: string; void: { reason: string; actor_id: string; created_at: string } | null }
export type HeadLine = Record<'output_tax' | 'liability_adjustments' | 'liability' | 'itc_claimed' | 'itc_reversal' | 'other_credit' | 'opening_credit' | 'credit' | 'net', string>;
export interface SetoffRuleRef { value: Record<string, unknown> & { steps?: string[]; multiple?: string; direction?: string }; source_reference: string; effective_from: string; rule_id: string }
export interface SetoffResult { version: string; status: 'computed' | 'not_computed'; reason?: string; rounding_note?: string; utilisation?: { credit_head: string; liability_head: string; amount: string }[]; heads?: Record<string, Record<'liability' | 'credit' | 'cash_before_rounding' | 'cash' | 'rounding_difference' | 'carry_forward', string>>; total_cash?: string; total_cash_before_rounding?: string; total_carry_forward?: string; rules?: Partial<Record<'credit_utilisation_order' | 'payment_rounding', SetoffRuleRef>> }
export interface WorksheetPayload { worksheet: { engine_version: string; heads: Record<string, HeadLine> } | null; setoff?: SetoffResult; gstr3b?: Gstr3bView; counts: { sales_rows: number; sales_included: number; sales_pending: number; sales_excluded: number; itc: Record<string, number> } }
export interface WorksheetPreview { notice: string; payload: WorksheetPayload; blockers: string[]; fingerprint: string; engine_version: string }
export interface FilingEvidenceEntry { id: string; arn: string; filed_on: string; note: string; label: string; created_at: string }
export interface TaxDraft { id: string; actor_id?: string; state: 'draft' | 'approved' | 'approved_stale' | 'reopened'; sales_batch_id: string; run_id: string; fingerprint: string; blockers: string[]; payload: WorksheetPayload; created_at: string; approval: { id: string; note: string; actor_id: string; created_at: string; reopen: { reason: string; created_at: string } | null; filing_evidence: FilingEvidenceEntry[] } | null }
export interface AuditEntry { id: string; action: string; resource_type: string; resource_id: string; summary: string | null; actor: string | null; period_code: string | null; client_name: string | null; created_at: string }

// The Board: per client-period workstream status from persisted records
export interface BoardCell { tone: 'done' | 'action' | 'blocked' | 'waiting'; label: string; target: 'sales' | 'workspace' | 'worksheet' }
export interface DueChip { date: string; days_left: number; tone: BoardCell['tone']; label: string }
export interface BoardRow { period_id: string; period_code: string; client_id: string; client_name: string; registration: string; sales: BoardCell; purchases: BoardCell; worksheet: BoardCell; due: { gstr1: DueChip; gstr3b: DueChip; source: string } | null; assignee: { id: string; name: string } | null }
export const boardApi = { get: (): Promise<BoardRow[]> => fetchApi('/board') };

// Assistants: brief, savings, ITC suggestions, investigator, follow-ups, column mapping, ask, knowledge rules
export interface BriefItem { text: string; href: string; tone: 'done' | 'action' | 'blocked' | 'waiting' }
export interface SavingsItem { kind: string; title: string; amount: string; detail: string; action: string; needs_ca: boolean; evidence: string[] }
export interface PeriodSavings { period_id: string; period_code: string; total: string; items: SavingsItem[]; notice: string }
export interface OrgSavings { total: string; periods: { period_id: string; period_code: string; client_name: string; total: string; items: number }[] }
export interface ItcSuggestion { result_id: string; status: string; decision: string; reason: string }
export interface InvestigationRecord { record_id: string; side: string; supplier_ref: string; invoice_number: string; invoice_date: string; invoice_total: string }
export interface Investigation { summary: string; findings: string[]; candidates: { record: InvestigationRecord; reasons: string[]; differences: Record<string, string> }[]; suggested_note: string }
export interface FollowupDraft { supplier_ref: string; supplier_name: string; invoices: number; credit_at_risk: string; message: string }
export interface MappingProposal { template: string; mapping: Record<string, string | null>; unused_headers: string[]; missing_required: string[]; source_headers: string[]; fields: string[]; optional: string[] }
export interface AskAnswer { intent: string | null; answer: string; citations: { label: string; ref: string }[]; suggestions?: string[] }
export interface KnowledgeRule { id: string; client_id: string | null; client_name: string | null; note: string; rule_kind: 'adjustment' | 'reminder'; frequency: 'monthly' | 'quarterly' | 'one_time'; adjustment_type: string | null; tax_head: string | null; amount: string | null; effective_from: string | null; effective_to: string | null; status: string; created_at: string; missing?: string[]; applied?: boolean; acknowledged?: { note: string; created_at: string } | null }
export interface RuleConfirmInput { rule_kind: 'adjustment' | 'reminder'; frequency: string; adjustment_type?: string | null; tax_head?: string | null; amount?: string | null; effective_from: string; effective_to?: string | null }
export interface LegalRuleEntry { key: string; title: string; help: string; fields: Record<string, 'int' | 'decimal' | 'list' | 'steps' | 'choice'>; options?: Record<string, string[]>; active: LegalVersion | null; history: LegalVersion[] }
export interface LegalVersion { id: string; key: string; value: Record<string, unknown>; source_reference: string; effective_from: string; status: string; confirmed_at: string }
const form = (data: Record<string, string | Blob>) => { const f = new FormData(); Object.entries(data).forEach(([k, v]) => f.append(k, v)); return f; };
export const assistApi = {
  brief: (): Promise<{ items: BriefItem[]; source: string }> => fetchApi('/brief'),
  orgSavings: (): Promise<OrgSavings> => fetchApi('/savings'),
  periodSavings: (periodId: string): Promise<PeriodSavings> => fetchApi(`/periods/${periodId}/savings`),
  itcSuggestions: (runId: string): Promise<{ suggestions: ItcSuggestion[]; counts: Record<string, number> }> => fetchApi(`/runs/${runId}/itc-suggestions`),
  investigate: (runId: string, resultId: string): Promise<Investigation> => fetchApi(`/runs/${runId}/results/${resultId}/investigate`),
  followups: (runId: string): Promise<{ drafts: FollowupDraft[] }> => fetchApi(`/runs/${runId}/supplier-followups`),
  proposeMapping: (template: string, file: File): Promise<MappingProposal> => fetchApi('/column-mapping/propose', { method: 'POST', body: form({ template, file }) }),
  applyMapping: async (template: string, mapping: Record<string, string | null>, file: File): Promise<File> => {
    const text: string = await fetchApi('/column-mapping/apply', { method: 'POST', body: form({ template, mapping: JSON.stringify(mapping), file }) });
    return new File([text], file.name.replace(/\.[^.]+$/, '') + '_mapped.csv', { type: 'text/csv' });
  },
  ask: (periodId: string, question: string, salesBatchId?: string, runId?: string): Promise<AskAnswer> => fetchApi(`/periods/${periodId}/ask`, json('POST', { question, sales_batch_id: salesBatchId || null, run_id: runId || null })),
  rules: (): Promise<KnowledgeRule[]> => fetchApi('/knowledge-rules'),
  draftRule: (clientId: string | null, note: string): Promise<KnowledgeRule> => fetchApi('/knowledge-rules/draft', json('POST', { client_id: clientId, note })),
  confirmRule: (id: string, data: RuleConfirmInput): Promise<KnowledgeRule> => fetchApi(`/knowledge-rules/${id}/confirm`, json('POST', data)),
  acknowledgeRule: (id: string, periodId: string, note: string) => fetchApi(`/knowledge-rules/${id}/acknowledge`, json('POST', { period_id: periodId, note })),
  legalRules: (): Promise<{ rules: LegalRuleEntry[]; notice: string }> => fetchApi('/legal-rules'),
  confirmLegal: (key: string, value: Record<string, unknown>, source_reference: string, effective_from: string) => fetchApi(`/legal-rules/${key}/confirm`, json('POST', { value, source_reference, effective_from, checked_against_current_law: true })),
  retireLegal: (key: string) => fetchApi(`/legal-rules/${key}/retire`, { method: 'POST' }),
  closeRule: (id: string, action: 'dismiss' | 'retire'): Promise<KnowledgeRule> => fetchApi(`/knowledge-rules/${id}/${action}`, { method: 'POST' }),
  applicableRules: (periodId: string): Promise<KnowledgeRule[]> => fetchApi(`/periods/${periodId}/applicable-rules`),
  applyRule: (id: string, periodId: string) => fetchApi(`/knowledge-rules/${id}/apply`, json('POST', { period_id: periodId })),
};

// Authentication
export type Role = 'owner' | 'reviewer' | 'preparer';
export interface Me { id: string; email: string; display_name: string; role: Role; firm: string | null; require_separate_approver: boolean }
export const authApi = {
  login: (email: string, password: string): Promise<Me> => fetchApi('/auth/login', json('POST', { email, password })),
  logout: () => fetchApi('/auth/logout', { method: 'POST' }),
  me: (): Promise<Me> => fetchApi('/auth/me'),
};
export interface CarryForward { status: 'available' | 'already_entered' | 'nothing_to_carry' | 'not_available'; from_period: string; reason?: string; draft_id?: string; amounts?: Record<string, string>; existing: TaxAdjustment[] }
export const carryApi = { get: (periodId: string): Promise<CarryForward> => fetchApi(`/periods/${periodId}/carry-forward`), apply: (periodId: string): Promise<CarryForward> => fetchApi(`/periods/${periodId}/carry-forward`, { method: 'POST' }) };
export interface FirmUser { id: string; email: string; display_name: string; role: Role; is_active: boolean }
export interface Firm { name: string; require_separate_approver: boolean; users: FirmUser[] }
export const firmApi = {
  get: (): Promise<Firm> => fetchApi('/firm'),
  settings: (require_separate_approver: boolean): Promise<Firm> => fetchApi('/firm/settings', json('PATCH', { require_separate_approver })),
  addUser: (data: { email: string; display_name: string; role: Role; initial_password: string }): Promise<FirmUser> => fetchApi('/firm/users', json('POST', data)),
  changeUser: (id: string, data: Partial<Pick<FirmUser, 'role' | 'is_active' | 'display_name'>>): Promise<FirmUser> => fetchApi(`/firm/users/${id}`, json('PATCH', data)),
  assign: (periodId: string, user_id: string | null) => fetchApi(`/periods/${periodId}/assign`, json('POST', { user_id })),
};export interface ImsItem { id: string; record_id: string; supplier_ref: string; invoice_number: string; invoice_date: string; taxable_value: string; tax: string; finding: string | null; action: 'accept' | 'reject' | 'pending' | null; previous_action_id: string | null; history: { id: string; action: string; note: string; actor_id: string; created_at: string }[] }
export interface ImsInbox { batch_id: string; run_id: string | null; items: ImsItem[]; counts: Record<'accept' | 'reject' | 'pending' | 'no_action', number>; notice: string }
export const imsApi = {
  get: (batchId: string): Promise<ImsInbox> => fetchApi(`/imports/${batchId}/ims`),
  act: (batchId: string, items: { record_id: string; action: string; previous_action_id: string | null }[], note: string) => fetchApi(`/imports/${batchId}/ims`, json('POST', { items, note })),
};export type G3Row = { label: string; taxable_value: string | null; igst: string | null; cgst: string | null; sgst: string | null; cess: string | null };
export interface Gstr3bView { version: string; status: 'available' | 'not_available'; reason?: string; table_3_1?: G3Row[]; table_4?: G3Row[]; table_6_1?: { head: string; tax_payable: string; paid_through_itc: Record<string, string>; paid_in_cash: string; interest: null; late_fee: null }[] | null; table_6_1_note?: string | null; notice?: string }export interface Gstr2bConversion { converted: number; skipped: { invoice: string; reason: string }[]; itc_unavailable: { record_id: string; invoice: string; reason: string }[]; notice: string }
export interface PublicLink { firm: string; client: string; period_code: string; kind: 'sales' | 'purchase'; what: string; expires_at: string; uses_left: number }
export const publicUploadApi = {
  get: (token: string): Promise<PublicLink> => fetchApi(`/public/upload/${encodeURIComponent(token)}`),
  send: (token: string, file: File): Promise<{ status: string; message: string }> => { const form = new FormData(); form.append('file', file); return fetchApi(`/public/upload/${encodeURIComponent(token)}`, { method: 'POST', body: form }); },
};
export interface UploadLinkView { id: string; kind: 'sales' | 'purchase'; expires_at: string; uses: number; max_uses: number; state: 'active' | 'expired' | 'used_up' | 'revoked'; created_at: string; path?: string }
export interface ReminderDraft { missing: string[]; subject: string | null; body: string | null; mailto: string | null; whatsapp: string | null; to_email?: string | null; to_phone?: string | null; note: string }
export const requestsApi = {
  links: (periodId: string): Promise<UploadLinkView[]> => fetchApi(`/periods/${periodId}/upload-links`),
  createLink: (periodId: string, kind: 'sales' | 'purchase', days = 7): Promise<UploadLinkView> => fetchApi(`/periods/${periodId}/upload-links`, json('POST', { kind, days })),
  revoke: (id: string): Promise<UploadLinkView> => fetchApi(`/upload-links/${id}/revoke`, { method: 'POST' }),
  reminder: (periodId: string, base_url: string): Promise<ReminderDraft> => fetchApi(`/periods/${periodId}/reminder`, json('POST', { base_url, include_links: true })),
  setContact: (clientId: string, contact_email: string, contact_phone: string) => fetchApi(`/clients/${clientId}/contact`, json('PATCH', { contact_email, contact_phone })),
};