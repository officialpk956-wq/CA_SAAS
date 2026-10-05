import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, ForeignKey, DateTime, Numeric, Text, Boolean, Integer, JSON, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # When on, a draft cannot be approved by the person who created it.
    require_separate_approver: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # null = cannot log in
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    role: Mapped[str] = mapped_column(String, nullable=False, default="owner", server_default="owner")  # owner, reviewer, preparer
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    
class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # for reminder drafts only
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class GSTRegistration(Base):
    __tablename__ = "gst_registrations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    gstin: Mapped[str] = mapped_column(String, nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class FilingPeriod(Base):
    __tablename__ = "filing_periods"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gst_registrations.id"), nullable=False)
    period_code: Mapped[str] = mapped_column(String, nullable=False) # e.g. "2026-08"
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def status(self) -> str:
        return "open"  # MVP: all periods are open

class SourceFile(Base):
    __tablename__ = "source_files"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id"), nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False) # 'purchase' or 'statement'
    status: Mapped[str] = mapped_column(String, default="preview") # preview, committed
    commit_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ImportRecord(Base):
    __tablename__ = "import_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_data: Mapped[dict] = mapped_column(JSON) # Store raw dict
    
    # Normalized fields for matching if valid
    record_id: Mapped[str | None] = mapped_column(String)
    document_type: Mapped[str | None] = mapped_column(String)
    supplier_ref: Mapped[str | None] = mapped_column(String)
    invoice_number: Mapped[str | None] = mapped_column(String)
    invoice_date: Mapped[str | None] = mapped_column(String)
    taxable_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    igst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cess: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    invoice_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_records.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id"), nullable=False)
    purchase_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    statement_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending") # pending, running, succeeded, failed
    error_message: Mapped[str | None] = mapped_column(Text)
    summary_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=False)
    result_id: Mapped[str] = mapped_column(String, nullable=False) # from engine
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    purchase_record_ids: Mapped[dict] = mapped_column(JSON) # list of original record IDs
    statement_record_ids: Mapped[dict] = mapped_column(JSON)
    validation_issues: Mapped[dict] = mapped_column(JSON)

class ResultDifference(Base):
    __tablename__ = "result_differences"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_results.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    difference_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

class ExceptionResolution(Base):
    __tablename__ = "exception_resolutions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=False)
    result_id: Mapped[str] = mapped_column(String, nullable=False) # engine result_id string
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False) # investigating, explained, correction_required
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    period_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("filing_periods.id"), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # short description; never full row contents
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CategoryProposal(Base):
    __tablename__ = "category_proposals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_records.id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CategoryDecision(Base):
    __tablename__ = "category_decisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_records.id"), nullable=False)
    proposal_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("category_proposals.id"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CategoryRule(Base):
    __tablename__ = "category_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    supplier_ref: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SalesBatch(Base):
    __tablename__ = 'sales_batches'
    __table_args__ = (UniqueConstraint('period_id','file_hash',name='uq_sales_period_hash'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'),nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    filename: Mapped[str] = mapped_column(String,nullable=False)
    file_hash: Mapped[str] = mapped_column(String,nullable=False)
    original_csv: Mapped[str] = mapped_column(Text,nullable=False)
    contract_version: Mapped[str] = mapped_column(String,nullable=False)
    status: Mapped[str] = mapped_column(String,nullable=False,default='preview')
    commit_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class SalesRecord(Base):
    __tablename__ = 'sales_records'
    __table_args__ = (UniqueConstraint('batch_id','row_number',name='uq_sales_batch_row'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('sales_batches.id'),nullable=False,index=True)
    row_number: Mapped[int] = mapped_column(Integer,nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON,nullable=False)
    validation_status: Mapped[str] = mapped_column(String,nullable=False)
    issues: Mapped[list] = mapped_column(JSON,nullable=False)

class SalesReview(Base):
    __tablename__ = 'sales_reviews'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('sales_records.id'),nullable=False,index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    decision: Mapped[str] = mapped_column(String,nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)


class ItcDecision(Base):
    __tablename__ = 'itc_decisions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reconciliation_runs.id'),nullable=False,index=True)
    result_id: Mapped[str] = mapped_column(String,nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    decision: Mapped[str] = mapped_column(String,nullable=False)  # claim, not_claimed, deferred
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class Adjustment(Base):
    __tablename__ = 'tax_adjustments'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'),nullable=False,index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String,nullable=False)
    tax_head: Mapped[str] = mapped_column(String,nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('knowledge_rules.id'),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class AdjustmentVoid(Base):
    __tablename__ = 'tax_adjustment_voids'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    adjustment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tax_adjustments.id'),nullable=False,unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    reason: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class TaxDraft(Base):
    __tablename__ = 'tax_drafts'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'),nullable=False,index=True)
    sales_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('sales_batches.id'),nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reconciliation_runs.id'),nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    engine_version: Mapped[str] = mapped_column(String,nullable=False)
    fingerprint: Mapped[str] = mapped_column(String,nullable=False)
    payload: Mapped[dict] = mapped_column(JSON,nullable=False)  # worksheet lines + contributing inputs
    blockers: Mapped[list] = mapped_column(JSON,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class TaxApproval(Base):
    __tablename__ = 'tax_approvals'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tax_drafts.id'),nullable=False,unique=True)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'),nullable=False,index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class TaxReopen(Base):
    __tablename__ = 'tax_reopens'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tax_approvals.id'),nullable=False,unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    reason: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class FilingEvidence(Base):
    __tablename__ = 'filing_evidence'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tax_approvals.id'),nullable=False,index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    arn: Mapped[str] = mapped_column(String,nullable=False)
    filed_on: Mapped[str] = mapped_column(String,nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)


class KnowledgeRule(Base):
    """A client quirk captured as a structured, human-confirmed monthly adjustment template."""
    __tablename__ = 'knowledge_rules'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('clients.id'),nullable=True,index=True)  # null = firm-wide
    rule_kind: Mapped[str] = mapped_column(String,nullable=False,default='adjustment')  # adjustment, reminder
    frequency: Mapped[str] = mapped_column(String,nullable=False,default='monthly')  # monthly, quarterly, one_time
    effective_to: Mapped[Optional[str]] = mapped_column(String)  # YYYY-MM, inclusive
    note: Mapped[str] = mapped_column(Text,nullable=False)
    adjustment_type: Mapped[Optional[str]] = mapped_column(String)
    tax_head: Mapped[Optional[str]] = mapped_column(String)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14,2))
    effective_from: Mapped[Optional[str]] = mapped_column(String)  # YYYY-MM
    status: Mapped[str] = mapped_column(String,nullable=False,default='proposed')  # proposed, active, dismissed, retired
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('users.id'))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)


class RuleAcknowledgement(Base):
    """A person confirming a reminder rule was checked for one period."""
    __tablename__ = 'rule_acknowledgements'
    __table_args__ = (UniqueConstraint('rule_id','period_id',name='uq_rule_ack_period'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('knowledge_rules.id'),nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'),nullable=False,index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class LegalRule(Base):
    """A statutory parameter entered and confirmed by the firm's CA, with its source. Versioned: a new
    confirmation retires the previous active version of the same key."""
    __tablename__ = 'legal_rules'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    key: Mapped[str] = mapped_column(String,nullable=False)
    value: Mapped[dict] = mapped_column(JSON,nullable=False)
    source_reference: Mapped[str] = mapped_column(Text,nullable=False)
    effective_from: Mapped[str] = mapped_column(String,nullable=False)
    status: Mapped[str] = mapped_column(String,nullable=False,default='active')  # active, retired
    confirmed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)


class UserSession(Base):
    """A login session. Only the SHA-256 of the browser's token is stored."""
    __tablename__ = 'user_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'),nullable=False,index=True)
    token_hash: Mapped[str] = mapped_column(String,nullable=False,unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ImsAction(Base):
    """IMS decision on one supplier invoice (a valid record of a committed statement import). Append-only; latest applies."""
    __tablename__ = 'ims_actions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('import_records.id'), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # accept, reject, pending
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UploadLink(Base):
    """A client-facing upload link for one period and file kind. Only the token's SHA-256 is stored."""
    __tablename__ = 'upload_links'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('filing_periods.id'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # sales, purchase
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)