export type Client = {
  id: string;
  name: string;
  type: string;
  reference: string;
  sales: string;
  purchases: string;
  worksheet: string;
  remarks: string;
  tone: "done" | "needs" | "blocked" | "waiting";
};

export type ReconRow = {
  id: string;
  purchase: string;
  statement: string;
  finding: string;
  state: string;
  taxable: number;
  difference: number;
};

export type ItcDecision = {
  id: string;
  finding: string;
  record: string;
  amount: number;
  decision: "claim" | "not_claimed" | "deferred" | "undecided";
};

export const periods = ["AUG 2026", "JUL 2026", "JUN 2026"];

export const clients: Client[] = [
  { id: "client-a", name: "Client A", type: "Retail", reference: "DEMO-REG-001", sales: "READY", purchases: "REVIEW 14 ROWS", worksheet: "25 ITC DECISIONS", remarks: "NEEDS YOU", tone: "needs" },
  { id: "client-b", name: "Client B", type: "E-commerce", reference: "DEMO-REG-002", sales: "READY", purchases: "MATCHED", worksheet: "READY FOR APPROVAL", remarks: "CHECK DRAFT", tone: "needs" },
  { id: "client-c", name: "Client C", type: "IT Services", reference: "DEMO-REG-003", sales: "READY", purchases: "MATCHED", worksheet: "APPROVED", remarks: "COMPLETE", tone: "done" },
  { id: "client-d", name: "Client D", type: "Manufacturing", reference: "DEMO-REG-004", sales: "8 INVALID", purchases: "AWAITING FILES", worksheet: "NOT STARTED", remarks: "WAITING", tone: "waiting" },
  { id: "client-e", name: "Client E", type: "Restaurant", reference: "DEMO-REG-005", sales: "READY", purchases: "3 DIFFERENCES", worksheet: "12 ITC DECISIONS", remarks: "REVIEW", tone: "needs" },
  { id: "client-f", name: "Client F", type: "Wholesale", reference: "DEMO-REG-006", sales: "READY", purchases: "MATCHED", worksheet: "APPROVED", remarks: "FILED", tone: "done" },
  { id: "client-g", name: "Client G", type: "Consultancy", reference: "DEMO-REG-007", sales: "AWAITING FILE", purchases: "MATCHED", worksheet: "NOT STARTED", remarks: "WAITING", tone: "waiting" },
  { id: "client-h", name: "Client H", type: "Logistics", reference: "DEMO-REG-008", sales: "READY", purchases: "BLOCKED", worksheet: "BLOCKED", remarks: "RE-UPLOAD", tone: "blocked" },
];

export const attentionItems = [
  { client: "Client A", need: "Decide 25 ITC findings", count: "25 OPEN" },
  { client: "Client B", need: "Approve worksheet draft", count: "1 DRAFT" },
  { client: "Client E", need: "Explain three differences", count: "3 OPEN" },
];

export const delayedItems = ["Client H — purchase file failed validation, re-upload"];

export const sourceRows = [
  { id: "PUR-001", date: "02 AUG 2026", supplier: "Demo Paper Co.", taxable: 12500, tax: 2250, state: "Valid", note: "" },
  { id: "PUR-002", date: "04 AUG 2026", supplier: "Example Systems", taxable: 8200, tax: 1476, state: "Invalid", note: "Invoice date is outside selected period" },
  { id: "PUR-003", date: "09 AUG 2026", supplier: "Sample Freight", taxable: 4700, tax: 846, state: "Invalid", note: "Duplicate document number" },
  { id: "PUR-004", date: "12 AUG 2026", supplier: "Mock Office Mart", taxable: 3100, tax: 558, state: "Invalid", note: "Tax head total does not reconcile" },
  { id: "PUR-005", date: "18 AUG 2026", supplier: "Demo Works", taxable: 9800, tax: 1764, state: "Valid", note: "" },
];

export const runHistory = [
  { id: "RUN-2508-03", time: "29 AUG 2026 · 18:42", detail: "40 rows · 7 exact · 25 groups", state: "Current" },
  { id: "RUN-2508-02", time: "27 AUG 2026 · 12:18", detail: "38 rows · 6 exact · 24 groups", state: "Superseded" },
  { id: "RUN-2508-01", time: "24 AUG 2026 · 09:05", detail: "35 rows · 5 exact · 22 groups", state: "Superseded" },
];

export const reconRows: ReconRow[] = [
  { id: "RES-001", purchase: "PUR-001", statement: "STM-021", finding: "matched", state: "unresolved", taxable: 12500, difference: 0 },
  { id: "RES-002", purchase: "PUR-002", statement: "STM-024", finding: "amount_mismatch", state: "investigating", taxable: 8200, difference: -200 },
  { id: "RES-003", purchase: "PUR-003", statement: "STM-025", finding: "date_conflict", state: "unresolved", taxable: 4700, difference: 0 },
  { id: "RES-004", purchase: "PUR-004", statement: "—", finding: "books_only", state: "correction_required", taxable: 3100, difference: 3100 },
  { id: "RES-005", purchase: "—", statement: "STM-031", finding: "statement_only", state: "unresolved", taxable: 9800, difference: -9800 },
  { id: "RES-006", purchase: "PUR-006", statement: "STM-034", finding: "duplicate_candidate", state: "explained", taxable: 2200, difference: 0 },
  { id: "RES-007", purchase: "PUR-007", statement: "—", finding: "validation_error", state: "correction_required", taxable: 6400, difference: 6400 },
];

export const reviewNotes = [
  { time: "29 AUG · 18:52", note: "Supplier statement is lower by ₹200. Asked client to confirm debit note.", author: "Priya" },
  { time: "28 AUG · 11:10", note: "Invoice number and date align; taxable value differs.", author: "Aman" },
];

export const salesRows = [
  { id: "SAL-001", date: "03 AUG 2026", customer: "Walk-in sales", kind: "B2C", taxable: 1000, tax: 180, status: "Reviewed" },
  { id: "SAL-002", date: "08 AUG 2026", customer: "Demo Buyer", kind: "B2B", taxable: 750, tax: 135, status: "Unresolved" },
  { id: "SAL-003", date: "08 AUG 2026", customer: "Demo Buyer", kind: "B2B", taxable: 750, tax: 135, status: "Duplicate" },
  { id: "SAL-004", date: "14 AUG 2026", customer: "Export Sample", kind: "Export", taxable: 500, tax: 0, status: "Excluded" },
  { id: "SAL-005", date: "19 AUG 2026", customer: "Counter sale", kind: "B2C", taxable: 460, tax: 82.8, status: "Invalid" },
];

export const salesSummary = [
  { label: "Rows", value: "19" }, { label: "Ready", value: "5" }, { label: "Invalid", value: "8" },
  { label: "Duplicate", value: "4" }, { label: "Unsupported", value: "2" },
];

export const receiptTotals = [
  { label: "Taxable", value: 1750 }, { label: "CGST", value: 112.5 }, { label: "SGST", value: 112.5 },
  { label: "IGST", value: 90 }, { label: "Cess", value: 0 }, { label: "Total", value: 2065 },
];

const findings = ["matched", "amount_mismatch", "date_conflict", "duplicate_candidate", "books_only", "statement_only"];
export const initialItcDecisions: ItcDecision[] = Array.from({ length: 25 }, (_, index) => ({
  id: `ITC-${String(index + 1).padStart(3, "0")}`,
  finding: findings[index % findings.length] ?? "matched",
  record: `PUR-${String(index + 1).padStart(3, "0")}`,
  amount: 90 + index * 17.5,
  decision: index < 7 ? "undecided" : index < 13 ? "not_claimed" : index < 18 ? "deferred" : "undecided",
}));

export const adjustmentTypes = ["Reverse-charge liability", "Other liability", "ITC reversal", "Other credit"];
export const taxHeads = ["IGST", "CGST", "SGST", "CESS"];

export const worksheetRows = [
  { head: "IGST", output: 90, liabilityAdj: 0, liability: 90, itc: 0, reversal: 0, creditAdj: 0, credit: 0, net: 90 },
  { head: "CGST", output: 112.5, liabilityAdj: 5, liability: 117.5, itc: 90, reversal: 0, creditAdj: 0, credit: 90, net: 27.5 },
  { head: "SGST", output: 112.5, liabilityAdj: 0, liability: 112.5, itc: 90, reversal: 0, creditAdj: 0, credit: 90, net: 22.5 },
  { head: "CESS", output: 0, liabilityAdj: 0, liability: 0, itc: 0, reversal: 0, creditAdj: 0, credit: 0, net: 0 },
];

export const priorDrafts = [
  { id: "DRF-202608-003", time: "29 AUG 2026 · 19:06", state: "OUT OF DATE", by: "Priya Shah" },
  { id: "DRF-202608-002", time: "28 AUG 2026 · 16:44", state: "REOPENED", by: "Aman Rao" },
  { id: "DRF-202608-001", time: "26 AUG 2026 · 10:12", state: "Draft", by: "Priya Shah" },
];

export const categoryRows = [
  { id: "PUR-001", supplier: "Demo Paper Co.", narration: "Packing material", suggested: "Consumables", source: "approved mapping", state: "Pending" },
  { id: "PUR-002", supplier: "Example Systems", narration: "Annual software plan", suggested: "Software", source: "mock model", state: "Pending" },
  { id: "PUR-003", supplier: "Sample Freight", narration: "Inbound transport", suggested: "Freight", source: "approved mapping", state: "Accepted" },
  { id: "PUR-004", supplier: "Mock Office Mart", narration: "Miscellaneous item", suggested: "—", source: "abstained", state: "Pending" },
];

export const mappings = [
  { supplier: "Demo Paper Co.", category: "Consumables", effective: "01 APR 2026", status: "Active" },
  { supplier: "Sample Freight", category: "Freight", effective: "18 JUL 2026", status: "Active" },
  { supplier: "Demo Works", category: "Repairs", effective: "02 AUG 2026", status: "Active" },
];

export const auditEvents = [
  { day: "29 AUG 2026", time: "19:06:42", action: "DRAFT SAVED", client: "Client A · AUG 2026", detail: "Worksheet DRF-202608-003 saved with 25 decisions", actor: "Priya Shah" },
  { day: "29 AUG 2026", time: "18:52:09", action: "REVIEW NOTE", client: "Client A · AUG 2026", detail: "Result RES-002 marked investigating", actor: "Priya Shah" },
  { day: "29 AUG 2026", time: "18:42:33", action: "RUN COMPLETE", client: "Client A · AUG 2026", detail: "RUN-2508-03 produced 25 result groups", actor: "Aman Rao" },
  { day: "28 AUG 2026", time: "16:44:01", action: "APPROVAL REOPENED", client: "Client A · AUG 2026", detail: "Sales input changed after approval", actor: "Aman Rao" },
  { day: "28 AUG 2026", time: "11:10:18", action: "ROW EXPLAINED", client: "Client E · AUG 2026", detail: "Date difference confirmed with client", actor: "Priya Shah" },
  { day: "27 AUG 2026", time: "12:18:55", action: "IMPORT COMMITTED", client: "Client B · AUG 2026", detail: "Purchase register version V2 committed", actor: "Aman Rao" },
];

export const screenCopy = {
  board: ["The Board", "Monthly work departures · August 2026"],
  clients: ["Clients", "Eight active demo workspaces"],
  workspace: ["Client A · August 2026", "Period workspace · DEMO-REG-001"],
  reconciliation: ["Reconciliation", "Trace every finding to its source"],
  sales: ["Sales", "Review the August sales register"],
  worksheet: ["Tax Worksheet", "Build, review and explicitly approve"],
  categories: ["Categories", "Confirm suggestions and maintain mappings"],
  history: ["History & Audit", "A continuous trace of human decisions"],
};