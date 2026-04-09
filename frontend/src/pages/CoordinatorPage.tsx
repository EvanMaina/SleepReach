/**
 * CoordinatorPage — Full-featured lead management dashboard
 *
 * Replicates NeuroReach coordinator features:
 * - Column visibility settings gear (Task A)
 * - Action icons: Call (3CX), SMS, Email, Eye/View (Task B)
 * - QuickActionPanel for call outcome recording (Task C)
 * - ConsultationPanel for scheduled lead outcomes (Task C)
 * - LeadDetailModal with notes, edit, delete (Task C)
 * - SMS & Email compose dialogs
 */

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  Headphones,
  UserPlus,
  TrendingUp,
  Phone,
  Volume2,
  VolumeX,
  MessageSquare,
  Mail,
  Search,
  Shield,
  Plus,
  ChevronRight,
  ChevronLeft,
  ChevronUp,
  ChevronDown,
  CheckCircle2,
  Filter,
  RefreshCw,
  Inbox,
  Settings,
  Eye,
  X,
  Flame,
  Zap,
  Calendar,
  Clock,
  User,
  ExternalLink,
  PhoneCall,
  PhoneMissed,
  PhoneOff,
  Ban,
  Stethoscope,
  CalendarPlus,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Loader2,
  FileText,
  Send,
  Edit2,
  Trash2,
  MapPin,
  UserCheck,
  XCircle,
  Tag,
  Paperclip,
  Download,
  Upload,
  Image,
  FileSpreadsheet,
} from "lucide-react";
import api, { leadsAPI, communicationsAPI } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { LeadEditModal } from "../components/dashboard/LeadEditModal";
import { ManualLeadModal } from "../components/dashboard/ManualLeadModal";
import { PhoneDialModal } from "../components/dashboard/PhoneDialModal";
import { QuickSMSModal } from "../components/dashboard/QuickSMSModal";
import {
  ATTACHMENTS_CHANGED_EVENT,
  deleteAttachment,
  downloadAttachment,
  formatFileSize,
  getAttachmentCounts,
  listAttachments,
  notifyAttachmentsChanged,
  uploadAttachment,
  type Attachment,
} from "../services/attachments";

/* ─────────────────────────────────────────────────────────────────────────── */
/* Types                                                                       */
/* ─────────────────────────────────────────────────────────────────────────── */
interface Lead {
  id: string;
  lead_number: string;
  first_name: string;
  last_name?: string;
  email?: string;
  phone?: string;
  condition?: string;
  conditions?: string[];
  other_condition_text?: string;
  condition_other?: string;
  priority: string;
  status: string;
  created_at: string;
  updated_at?: string;
  scheduled_callback_at?: string;
  contact_outcome?: string;
  contact_attempts?: number;
  last_contact_attempt?: string;
  last_updated_at?: string;
  preferred_contact_method?: string;
  is_referral?: boolean;
  referring_provider_name?: string;
  follow_up_reason?: string;
  source?: string;
  score?: number;
  lead_score?: number;
  zip_code?: string;
  in_service_area?: boolean;
  has_insurance?: boolean;
  insurance_provider?: string;
  symptom_duration?: string;
  prior_treatments?: string[];
  urgency?: string;
  notes?: string;
  hipaa_consent?: boolean;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  sleep_treatment_interest?: string;
}

interface LeadNote {
  id: string;
  lead_id: string;
  note_text: string;
  created_by: string | null;
  created_by_name: string;
  note_type: string;
  related_outcome: string | null;
  created_at: string;
}

const SLEEP_TREATMENT_LABELS: Record<string, string> = {
  cpap_bipap: "CPAP Therapy",
  inspire: "Inspire Therapy",
  therapy_cbt: "CBT-I Therapy",
  sleep_study: "Testing / Sleep Study",
  medication: "Medication Review",
  not_sure: "Not sure - I'd like to learn more",
};

interface EmailTemplate {
  id: string;
  label: string;
  description: string;
  subject: string;
  body: string;
}

interface SMSTemplate {
  id: string;
  label: string;
  description: string;
  message: string;
}

interface CoordinatorPageProps {
  forcedQueue?: string;
}

/* ─────────────────────────────────────────────────────────────────────────── */
/* Constants                                                                   */
/* ─────────────────────────────────────────────────────────────────────────── */
const COLUMN_KEYS = [
  "leadId",
  "patient",
  "condition",
  "priority",
  "status",
  "scheduledFor",
  "submitted",
  "lastActivity",
  "preferred",
  "actions",
] as const;
type ColKey = (typeof COLUMN_KEYS)[number];

const COLUMN_LABELS: Record<ColKey, string> = {
  leadId: "Lead ID",
  patient: "Patient",
  condition: "Condition",
  priority: "Priority",
  status: "Status",
  scheduledFor: "Scheduled For",
  submitted: "Submitted",
  lastActivity: "Last Activity",
  preferred: "Preferred",
  actions: "Actions",
};

const LOCKED_COLUMNS: ColKey[] = ["leadId", "patient"];

const CONTACT_OUTCOME_CONFIG: Record<
  string,
  { label: string; color: string; bgColor: string; borderColor: string }
> = {
  NEW: {
    label: "New",
    color: "text-blue-700",
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
  },
  ANSWERED: {
    label: "Answered",
    color: "text-emerald-700",
    bgColor: "bg-emerald-50",
    borderColor: "border-emerald-200",
  },
  NO_ANSWER: {
    label: "No Answer",
    color: "text-amber-700",
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
  },
  UNREACHABLE: {
    label: "Unreachable",
    color: "text-red-700",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
  },
  CALLBACK_REQUESTED: {
    label: "Callback",
    color: "text-violet-700",
    bgColor: "bg-violet-50",
    borderColor: "border-violet-200",
  },
  NOT_INTERESTED: {
    label: "Not Interested",
    color: "text-slate-700",
    bgColor: "bg-slate-100",
    borderColor: "border-slate-300",
  },
  SCHEDULED: {
    label: "Scheduled",
    color: "text-teal-700",
    bgColor: "bg-teal-50",
    borderColor: "border-teal-200",
  },
  COMPLETED: {
    label: "Completed",
    color: "text-green-700",
    bgColor: "bg-green-50",
    borderColor: "border-green-200",
  },
};

const QUICK_FILTERS = [
  { key: "All", icon: null, activeColor: "" },
  { key: "Hot", icon: Flame, activeColor: "bg-red-600" },
  { key: "Medium", icon: Zap, activeColor: "bg-amber-500" },
  { key: "Low", icon: User, activeColor: "bg-blue-500" },
  { key: "Scheduled", icon: Calendar, activeColor: "bg-violet-600" },
  { key: "Referral", icon: UserCheck, activeColor: "bg-emerald-600" },
];
const PAGE_SIZE = 50;

const QUEUE_META: Record<
  string,
  {
    title: string;
    subtitle: string;
    sectionTitle: string;
    sectionSubtitle: string;
    icon: typeof Headphones;
  }
> = {
  all: {
    title: "All Leads",
    subtitle: "Browse and manage all active SleepReach leads",
    sectionTitle: "All Leads",
    sectionSubtitle: "Unified view across every active coordinator queue",
    icon: UserCheck,
  },
  new: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "New Leads",
    sectionSubtitle: "Never contacted - first outreach needed",
    icon: Headphones,
  },
  contacted: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Contacted Leads",
    sectionSubtitle: "Active leads with at least one contact attempt",
    icon: Headphones,
  },
  follow_up: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Follow-up Queue",
    sectionSubtitle: "Leads waiting for the next outreach step",
    icon: Headphones,
  },
  callback: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Callback Queue",
    sectionSubtitle: "Leads with callbacks scheduled or requested",
    icon: Headphones,
  },
  scheduled: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Scheduled Queue",
    sectionSubtitle: "Upcoming consultations and callbacks to manage",
    icon: Headphones,
  },
  completed: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Completed Leads",
    sectionSubtitle:
      "Consultations finished and ready for downstream follow-through",
    icon: Headphones,
  },
  unreachable: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Unreachable Leads",
    sectionSubtitle: "Leads we could not reach after contact attempts",
    icon: Headphones,
  },
  not_interested: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Not Interested Leads",
    sectionSubtitle: "Leads who are not moving forward right now",
    icon: Headphones,
  },
  hot: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Hot Priority Leads",
    sectionSubtitle: "Highest-priority leads needing immediate attention",
    icon: Headphones,
  },
  medium: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Medium Priority Leads",
    sectionSubtitle: "Qualified leads with moderate urgency",
    icon: Headphones,
  },
  low: {
    title: "Coordinator Dashboard",
    subtitle: "Manage lead outreach queues and patient follow-ups",
    sectionTitle: "Low Priority Leads",
    sectionSubtitle: "Lower urgency leads still active in the funnel",
    icon: Headphones,
  },
};

/* ─────────────────────────────────────────────────────────────────────────── */
/* Helpers                                                                     */
/* ─────────────────────────────────────────────────────────────────────────── */
function priorityBadge(p: string) {
  const map: Record<string, string> = {
    HOT: "bg-red-50 text-red-700 ring-1 ring-red-200",
    MEDIUM: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    LOW: "bg-gray-50 text-gray-600 ring-1 ring-gray-200",
  };
  return map[p?.toUpperCase()] || map.LOW;
}

function statusBadge(s: string) {
  const map: Record<string, string> = {
    NEW: "bg-blue-50 text-blue-700",
    CONTACTED: "bg-indigo-50 text-indigo-700",
    SCHEDULED: "bg-green-50 text-green-700",
    CONSULTATION_COMPLETE: "bg-emerald-50 text-emerald-700",
    TREATMENT_STARTED: "bg-teal-50 text-teal-700",
  };
  return map[s] || "bg-gray-50 text-gray-600";
}

function conditionLabel(lead: Lead) {
  if (lead.conditions?.length)
    return lead.conditions.map((c) => c.replace(/_/g, " ")).join(", ");
  if (lead.condition) return lead.condition.replace(/_/g, " ");
  return "—";
}

function formatDate(d?: string) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeAgo(d?: string) {
  if (!d) return null;
  const diff = Date.now() - new Date(d).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatPhoneForTel(phone: string): string {
  const digits = phone.replace(/[^\d]/g, "");
  if (digits.startsWith("1") && digits.length === 11) return `tel:+${digits}`;
  if (digits.length === 10) return `tel:+1${digits}`;
  return `tel:+1${digits}`;
}

function noteTimeAgo(d: string): string {
  const diff = Date.now() - new Date(d).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(diff / 3600000);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(diff / 86400000);
  if (days < 7) return `${days}d ago`;
  return new Date(d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatPreferred(m?: string) {
  if (!m) return "—";
  const n = m.toLowerCase();
  if (n.includes("phone") || n === "call") return "Phone";
  if (n === "email") return "Email";
  if (n === "sms" || n === "text") return "Text";
  if (n === "any" || n === "no preference") return "Any";
  return m;
}

function treatmentInterestLabel(value?: string) {
  if (!value) return "—";
  return SLEEP_TREATMENT_LABELS[value] || value.replace(/_/g, " ");
}

function personalizeTemplate(text: string, lead?: Lead | null) {
  const firstName = lead?.first_name?.trim() || "there";
  return text
    .replace(/{{first_name}}/g, firstName)
    .replace(/{{clinic_phone}}/g, "(480) 745-3547")
    .replace(/{{clinic_name}}/g, "The Insomnia and Sleep Institute of Arizona");
}

function attachmentTypeLabel(mimeType: string): string {
  if (mimeType.startsWith("image/")) return "Image";
  if (mimeType.includes("pdf")) return "PDF";
  if (mimeType.includes("excel") || mimeType.includes("sheet"))
    return "Spreadsheet";
  if (mimeType.includes("word")) return "Document";
  return "File";
}

/* ─────────────────────────────────────────────────────────────────────────── */
/* Main Component                                                              */
/* ─────────────────────────────────────────────────────────────────────────── */
export default function CoordinatorPage({
  forcedQueue,
}: CoordinatorPageProps = {}) {
  const { user } = useAuth();
  const isAdmin =
    user?.role === "administrator" || user?.role === "primary_admin";

  // ── Data ────────────────────────────────────────────────────────────────
  const [leads, setLeads] = useState<Lead[]>([]);
  const { queue: urlQueue } = useParams<{ queue?: string }>();
  const activeQueue = forcedQueue || urlQueue || "new";
  const pageMeta = QUEUE_META[activeQueue] || QUEUE_META.new;
  const [activeFilter, setActiveFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [sortField, setSortField] = useState<string>("lastUpdatedAt");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [tablePage, setTablePage] = useState(1);

  // ── Column Visibility (Task A) ──────────────────────────────────────────
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(
    new Set(COLUMN_KEYS),
  );
  const [showColToggle, setShowColToggle] = useState(false);
  const colToggleRef = useRef<HTMLDivElement>(null);

  // ── Column Resizing ───────────────────────────────────────────────────
  const DEFAULT_COL_WIDTHS: Record<ColKey, number> = {
    leadId: 120, patient: 180, condition: 200, priority: 90,
    status: 130, scheduledFor: 140, submitted: 140,
    lastActivity: 120, preferred: 90, actions: 140,
  };
  const [colWidths, setColWidths] = useState<Record<string, number>>(DEFAULT_COL_WIDTHS);
  const resizingCol = useRef<string | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartW = useRef(0);

  const handleResizeStart = useCallback((col: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizingCol.current = col;
    resizeStartX.current = e.clientX;
    resizeStartW.current = colWidths[col] || 120;
    const onMove = (ev: MouseEvent) => {
      if (!resizingCol.current) return;
      const delta = ev.clientX - resizeStartX.current;
      const newW = Math.max(60, resizeStartW.current + delta);
      setColWidths((prev) => ({ ...prev, [resizingCol.current!]: newW }));
    };
    const onUp = () => {
      resizingCol.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [colWidths]);

  // ── Panels (Task C) ────────────────────────────────────────────────────
  const [quickActionLead, setQuickActionLead] = useState<Lead | null>(null);
  const [consultationLead, setConsultationLead] = useState<Lead | null>(null);
  const [detailLead, setDetailLead] = useState<Lead | null>(null);
  const [detailNotes, setDetailNotes] = useState<LeadNote[]>([]);
  const [detailNotesLoading, setDetailNotesLoading] = useState(false);
  const [detailNewNote, setDetailNewNote] = useState("");
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [editLead, setEditLead] = useState<Lead | null>(null);
  const [showManualLeadModal, setShowManualLeadModal] = useState(false);
  const [attachmentCounts, setAttachmentCounts] = useState<
    Record<string, number>
  >({});
  const [detailAttachments, setDetailAttachments] = useState<Attachment[]>([]);
  const [detailAttachmentsLoading, setDetailAttachmentsLoading] =
    useState(false);
  const [detailAttachmentUploading, setDetailAttachmentUploading] =
    useState(false);
  const [detailAttachmentDeleting, setDetailAttachmentDeleting] = useState<
    string | null
  >(null);
  const detailAttachmentInputRef = useRef<HTMLInputElement>(null);
  const [attachDropdownLeadId, setAttachDropdownLeadId] = useState<
    string | null
  >(null);
  const [attachDropdownPlacement, setAttachDropdownPlacement] = useState<
    "up" | "down"
  >("down");
  const [attachDropdownItems, setAttachDropdownItems] = useState<Attachment[]>(
    [],
  );
  const [attachDropdownLoading, setAttachDropdownLoading] = useState(false);
  const [attachDownloading, setAttachDownloading] = useState<string | null>(
    null,
  );
  const [attachDeleting, setAttachDeleting] = useState<string | null>(null);
  const [attachUploading, setAttachUploading] = useState(false);
  const [attachDeleteConfirm, setAttachDeleteConfirm] = useState<string | null>(
    null,
  );
  const attachDropdownRef = useRef<HTMLDivElement>(null);
  const attachFileInputRef = useRef<HTMLInputElement>(null);

  // ── SMS/Email Dialogs (Task B) ──────────────────────────────────────────
  const [smsDialogLead, setSmsDialogLead] = useState<Lead | null>(null);
  const [smsDialogOpen, setSmsDialogOpen] = useState(false);
  const [smsMessage, setSmsMessage] = useState("");
  const [smsSending, setSmsSending] = useState(false);
  const [quickCallOpen, setQuickCallOpen] = useState(false);
  const [quickSmsOpen, setQuickSmsOpen] = useState(false);
  const [emailDialogLead, setEmailDialogLead] = useState<Lead | null>(null);
  const [emailDialogOpen, setEmailDialogOpen] = useState(false);
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [emailSending, setEmailSending] = useState(false);
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [smsTemplates, setSmsTemplates] = useState<SMSTemplate[]>([]);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState("custom");
  const [selectedSmsTemplate, setSelectedSmsTemplate] = useState("custom");
  const templatesLoadedRef = useRef(false);
  const [isOpeningEdit, setIsOpeningEdit] = useState(false);

  // ── Toasts ──────────────────────────────────────────────────────────────
  const [toasts, setToasts] = useState<
    Array<{ id: number; message: string; type: "success" | "error" }>
  >([]);
  const toastId = useRef(0);
  const showToast = useCallback(
    (message: string, type: "success" | "error" = "success") => {
      const id = ++toastId.current;
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(
        () => setToasts((prev) => prev.filter((t) => t.id !== id)),
        3500,
      );
    },
    [],
  );

  // ── Debounced search ─────────────────────────────────────────────────────
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // ── Data Fetching ───────────────────────────────────────────────────────
  const fetchLeads = useCallback(async () => {
    setIsLoading(true);
    try {
      const [leadRes, countMap] = await Promise.all([
        api.get("/leads", {
          params: { queue_type: activeQueue, page_size: 200 },
        }),
        getAttachmentCounts().catch(() => ({})),
      ]);
      setLeads(leadRes.data?.items || []);
      setAttachmentCounts(countMap || {});
    } catch {
      setLeads([]);
      setAttachmentCounts({});
    } finally {
      setIsLoading(false);
    }
  }, [activeQueue]);

  // ── Real-Time Polling for New Leads ──────────────────────────────────────
  const lastLeadCountRef = useRef<number | null>(null);
  const soundEnabledRef = useRef(true);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const notifAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    // Premium notification chime (short, professional)
    notifAudioRef.current = new Audio("data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleRgAYJrl0I9cDACBnOPReXgAAIar5OiSdBQAgrHu9oRaAAB4jN/qql4AAHqX6/N+WgAAe5jn76BoJgB0luf0gGAEAHqT5fKGWxIAf5rn9IpeBgCFme/uhFkRAIia6PKNWQsAhJju8I5TBQCKmO3vkVcHAI2Z7PKPUQQAjJfs8pFUBgCOmOvykVACAJKZ6vKTUQIAkpjq8ZRQAQCUmOnxlE8AAJaY6fGWTwAAlpfp8ZZNAACYl+nxlkwAAJqX6PGXSwAAmZbo8ZhLAACbl+jxmEoAAJyW6PKZSgAAnJbm8ppJAACelubymiYRAJ6W5vKbJwkAoJbm8pwlCACglubyKw8AAJmV5fMsDwAAnJXl8y0NAACaleTzLg0AAJuV5fMvCgAAnJXk8zALAACcleT0MQgAAJ2V5PQyBwAAn5Xk9DQGAQD//w==");
    notifAudioRef.current.volume = 0.4;
    return () => { notifAudioRef.current = null; };
  }, []);

  useEffect(() => { soundEnabledRef.current = soundEnabled; }, [soundEnabled]);

  useEffect(() => {
    if (isLoading) return;
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/leads/latest-check");
        const total = res.data?.total ?? 0;
        const sources = res.data?.recent_sources ?? [];
        if (lastLeadCountRef.current !== null && total > lastLeadCountRef.current) {
          // New lead detected — check it's organic (not manual)
          const isOrganic = sources.some((s: string) => s !== "manual");
          if (isOrganic && soundEnabledRef.current && notifAudioRef.current) {
            notifAudioRef.current.currentTime = 0;
            notifAudioRef.current.play().catch(() => {});
          }
          // Silently refresh the lead list
          const [leadRes, countMap] = await Promise.all([
            api.get("/leads", { params: { queue_type: activeQueue, page_size: 200 } }),
            getAttachmentCounts().catch(() => ({})),
          ]);
          setLeads(leadRes.data?.items || []);
          setAttachmentCounts(countMap || {});
        }
        lastLeadCountRef.current = total;
      } catch { /* ignore polling errors */ }
    }, 10000);
    return () => clearInterval(interval);
  }, [activeQueue, isLoading]);

  const mergeLeadIntoState = useCallback(
    (updatedLead: Partial<Lead> & { id: string }) => {
      // CRITICAL FIX: Never add new rows — only update existing leads.
      // Adding non-existent leads causes ghost/empty rows when outcome
      // responses (especially consultation-outcome) return partial data.
      if (!updatedLead.id) return;
      setLeads((prev) =>
        prev.map((lead) =>
          lead.id === updatedLead.id
            ? ({ ...lead, ...updatedLead } as Lead)
            : lead,
        ),
      );
      setDetailLead((prev) =>
        prev && prev.id === updatedLead.id
          ? ({ ...prev, ...updatedLead } as Lead)
          : prev,
      );
    },
    [],
  );

  // After any outcome recording, remove the lead from the current queue
  // view (it moved to a different queue) and refetch to get accurate data.
  const handleOutcomeRecorded = useCallback(
    (leadId: string) => {
      setLeads((prev) => prev.filter((lead) => lead.id !== leadId));
      fetchLeads();
    },
    [fetchLeads],
  );

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);
  useEffect(() => {
    if (isLoading) return;
    const raw = sessionStorage.getItem("sleepreach_focus_lead");
    if (!raw) return;

    let cancelled = false;

    const openFocusedLead = async () => {
      try {
        const parsed = JSON.parse(raw) as { leadId?: string };
        if (!parsed.leadId) {
          sessionStorage.removeItem("sleepreach_focus_lead");
          return;
        }

        const existing = leads.find((lead) => lead.id === parsed.leadId);
        if (existing) {
          setQuickActionLead(existing);
          sessionStorage.removeItem("sleepreach_focus_lead");
          return;
        }

        const response = await leadsAPI.get(parsed.leadId);
        if (cancelled) return;
        setQuickActionLead(response.data);
        sessionStorage.removeItem("sleepreach_focus_lead");
      } catch {
        sessionStorage.removeItem("sleepreach_focus_lead");
      }
    };

    void openFocusedLead();
    return () => {
      cancelled = true;
    };
  }, [isLoading, leads, activeQueue]);
  useEffect(() => {
    setActiveFilter("All");
    setSearch("");
    setTablePage(1);
  }, [activeQueue]);
  // Close column toggle on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        colToggleRef.current &&
        !colToggleRef.current.contains(e.target as Node)
      )
        setShowColToggle(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Filtering & Sorting ─────────────────────────────────────────────────
  const filteredLeads = useMemo(() => {
    let result = leads;
    if (activeFilter === "Hot")
      result = result.filter((l) => l.priority === "HOT");
    else if (activeFilter === "Medium")
      result = result.filter((l) => l.priority === "MEDIUM");
    else if (activeFilter === "Low")
      result = result.filter((l) => l.priority === "LOW");
    else if (activeFilter === "Scheduled")
      result = result.filter((l) => l.status === "SCHEDULED");
    else if (activeFilter === "Referral")
      result = result.filter((l) => l.is_referral);
    if (debouncedSearch.trim()) {
      const s = debouncedSearch.toLowerCase();
      result = result.filter(
        (l) =>
          l.lead_number?.toLowerCase().includes(s) ||
          l.first_name?.toLowerCase().includes(s) ||
          l.last_name?.toLowerCase().includes(s) ||
          l.email?.toLowerCase().includes(s) ||
          l.phone?.toLowerCase().includes(s),
      );
    }
    // Sort
    const sorted = [...result].sort((a, b) => {
      let cmp = 0;
      const pOrder: Record<string, number> = { HOT: 1, MEDIUM: 2, LOW: 3 };
      if (sortField === "leadId")
        cmp = (a.lead_number || "").localeCompare(b.lead_number || "");
      else if (sortField === "firstName")
        cmp = `${a.first_name} ${a.last_name || ""}`.localeCompare(
          `${b.first_name} ${b.last_name || ""}`,
        );
      else if (sortField === "condition")
        cmp = conditionLabel(a).localeCompare(conditionLabel(b));
      else if (sortField === "priority")
        cmp = (pOrder[a.priority] || 9) - (pOrder[b.priority] || 9);
      else if (sortField === "status")
        cmp = (a.status || "").localeCompare(b.status || "");
      else if (sortField === "submittedAt")
        cmp =
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      else if (sortField === "lastUpdatedAt") {
        const at = a.last_updated_at
          ? new Date(a.last_updated_at).getTime()
          : 0;
        const bt = b.last_updated_at
          ? new Date(b.last_updated_at).getTime()
          : 0;
        cmp = at - bt;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [leads, activeFilter, debouncedSearch, sortField, sortDir]);

  useEffect(() => {
    setTablePage(1);
  }, [filteredLeads.length]);

  const totalPages = Math.max(1, Math.ceil(filteredLeads.length / PAGE_SIZE));
  const paginatedLeads = filteredLeads.slice(
    (tablePage - 1) * PAGE_SIZE,
    tablePage * PAGE_SIZE,
  );

  // ── Metrics ─────────────────────────────────────────────────────────────
  const isToday = (d: string) => {
    const dt = new Date(d),
      t = new Date();
    return (
      dt.getFullYear() === t.getFullYear() &&
      dt.getMonth() === t.getMonth() &&
      dt.getDate() === t.getDate()
    );
  };
  const inQueueCount = filteredLeads.length;
  const addedTodayCount = useMemo(() => {
    if (activeQueue === "new" || activeQueue === "all")
      return filteredLeads.filter((l) => isToday(l.created_at)).length;
    return filteredLeads.filter(
      (l) => l.last_updated_at && isToday(l.last_updated_at),
    ).length;
  }, [filteredLeads, activeQueue]);
  const responseRate = useMemo(() => {
    const contacted = filteredLeads.filter(
      (l) => l.contact_outcome && l.contact_outcome !== "NEW",
    );
    const answered = filteredLeads.filter(
      (l) => l.contact_outcome === "ANSWERED",
    );
    return contacted.length > 0
      ? Math.round((answered.length / contacted.length) * 100)
      : 0;
  }, [filteredLeads]);
  const conversionRate = useMemo(() => {
    if (filteredLeads.length === 0) return 0;
    if (activeQueue === "scheduled")
      return Math.round(
        (filteredLeads.filter(
          (l) =>
            l.status === "CONSULTATION_COMPLETE" ||
            l.status === "TREATMENT_STARTED",
        ).length /
          filteredLeads.length) *
          100,
      );
    if (activeQueue === "completed") return 100;
    return Math.round(
      (filteredLeads.filter(
        (l) =>
          l.status === "SCHEDULED" ||
          l.status === "CONSULTATION_COMPLETE" ||
          l.status === "TREATMENT_STARTED",
      ).length /
        filteredLeads.length) *
        100,
    );
  }, [filteredLeads, activeQueue]);

  const kpis = [
    {
      label: "In Queue",
      value: inQueueCount,
      icon: Headphones,
      gradient: "from-[#4A6FA5] to-[#6593be]",
    },
    {
      label: "Added Today",
      value: addedTodayCount,
      icon: UserPlus,
      gradient: "from-[#26a9b5] to-[#41c5cf]",
    },
    {
      label: "Response Rate",
      value: `${responseRate}%`,
      icon: TrendingUp,
      gradient: "from-[#EE9A1D] to-[#f2b034]",
    },
    {
      label: "Conversion Rate",
      value: `${conversionRate}%`,
      icon: CheckCircle2,
      gradient: "from-[#344d72] to-[#4A6FA5]",
    },
  ];

  // ── Handlers ────────────────────────────────────────────────────────────
  const handleSort = (field: string) => {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortField(field);
      // Time-based fields default to desc (newest first), others to asc
      if (field === "lastUpdatedAt" || field === "submittedAt") {
        setSortDir("desc");
        return;
      }
      setSortDir("asc");
    }
  };
  const getSortIcon = (field: string) => {
    if (sortField !== field)
      return <ChevronUp size={12} className="text-gray-300" />;
    return sortDir === "asc" ? (
      <ChevronUp size={12} className="text-sleep-600" />
    ) : (
      <ChevronDown size={12} className="text-sleep-600" />
    );
  };

  const handleOpenInteractionPanel = (lead: Lead) => {
    if (lead.status === "SCHEDULED") setConsultationLead(lead);
    else setQuickActionLead(lead);
  };

  const handleCallVia3CX = (phone: string) => {
    window.location.href = formatPhoneForTel(phone);
  };

  const loadDetailAttachments = useCallback(async (leadId: string) => {
    setDetailAttachmentsLoading(true);
    try {
      const items = await listAttachments(leadId);
      setDetailAttachments(items);
    } catch {
      setDetailAttachments([]);
    } finally {
      setDetailAttachmentsLoading(false);
    }
  }, []);

  useEffect(() => {
    const handler = async (event: Event) => {
      const leadId = (event as CustomEvent<{ leadId?: string }>).detail?.leadId;
      try {
        const counts = await getAttachmentCounts();
        setAttachmentCounts(counts);
      } catch {}
      if (leadId && detailLead?.id === leadId) {
        loadDetailAttachments(leadId);
      }
    };
    window.addEventListener(
      ATTACHMENTS_CHANGED_EVENT,
      handler as EventListener,
    );
    return () =>
      window.removeEventListener(
        ATTACHMENTS_CHANGED_EVENT,
        handler as EventListener,
      );
  }, [detailLead?.id, loadDetailAttachments]);

  useEffect(() => {
    if (!attachDropdownLeadId) return;
    const handler = (event: MouseEvent) => {
      if (
        attachDropdownRef.current &&
        !attachDropdownRef.current.contains(event.target as Node)
      ) {
        setAttachDropdownLeadId(null);
        setAttachDeleteConfirm(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [attachDropdownLeadId]);

  const openAttachDropdown = useCallback(
    async (leadId: string, triggerEl?: HTMLElement | null) => {
      if (attachDropdownLeadId === leadId) {
        setAttachDropdownLeadId(null);
        setAttachDeleteConfirm(null);
        return;
      }

      if (triggerEl) {
        const rect = triggerEl.getBoundingClientRect();
        const estimatedDropdownHeight = 340;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        setAttachDropdownPlacement(
          spaceBelow < estimatedDropdownHeight && spaceAbove > spaceBelow
            ? "up"
            : "down",
        );
      } else {
        setAttachDropdownPlacement("down");
      }

      setAttachDropdownLeadId(leadId);
      setAttachDeleteConfirm(null);
      setAttachDropdownLoading(true);
      setAttachDropdownItems([]);
      try {
        const items = await listAttachments(leadId);
        setAttachDropdownItems(items);
      } catch {
        setAttachDropdownItems([]);
      } finally {
        setAttachDropdownLoading(false);
      }
    },
    [attachDropdownLeadId],
  );

  const getAttachmentIcon = useCallback((mimeType: string) => {
    if (mimeType.startsWith("image/"))
      return <Image size={14} className="text-pink-500" />;
    if (
      mimeType.includes("spreadsheet") ||
      mimeType.includes("excel") ||
      mimeType.includes("sheet")
    )
      return <FileSpreadsheet size={14} className="text-green-600" />;
    if (mimeType.includes("pdf"))
      return <FileText size={14} className="text-red-500" />;
    return <FileText size={14} className="text-blue-500" />;
  }, []);

  const handleAttachmentDownload = useCallback(
    async (leadId: string, attachment: Attachment) => {
      setAttachDownloading(attachment.id);
      try {
        await downloadAttachment(leadId, attachment.id, attachment.filename);
      } catch {
        showToast("Failed to download attachment", "error");
      } finally {
        setAttachDownloading(null);
      }
    },
    [showToast],
  );

  const handleAttachmentDelete = useCallback(
    async (leadId: string, attachmentId: string) => {
      setAttachDeleting(attachmentId);
      try {
        await deleteAttachment(leadId, attachmentId);
        setAttachDropdownItems((prev) =>
          prev.filter((item) => item.id !== attachmentId),
        );
        setAttachmentCounts((prev) => {
          const nextCount = Math.max((prev[leadId] || 0) - 1, 0);
          if (nextCount === 0) {
            const next = { ...prev };
            delete next[leadId];
            return next;
          }
          return { ...prev, [leadId]: nextCount };
        });
        setAttachDeleteConfirm(null);
        if (detailLead?.id === leadId) {
          await loadDetailAttachments(leadId);
        }
        notifyAttachmentsChanged(leadId);
        showToast("Attachment deleted");
      } catch {
        showToast("Failed to delete attachment", "error");
      } finally {
        setAttachDeleting(null);
      }
    },
    [detailLead?.id, loadDetailAttachments, showToast],
  );

  const handleAttachmentUploadMore = useCallback(
    async (leadId: string, files: FileList) => {
      setAttachUploading(true);
      const newItems: Attachment[] = [];
      for (const file of Array.from(files)) {
        try {
          const uploaded = await uploadAttachment(leadId, file);
          newItems.push(uploaded);
        } catch {
          showToast(`Failed to upload ${file.name}`, "error");
        }
      }

      if (newItems.length > 0) {
        setAttachDropdownItems((prev) => [...newItems, ...prev]);
        setAttachmentCounts((prev) => ({
          ...prev,
          [leadId]: (prev[leadId] || 0) + newItems.length,
        }));
        if (detailLead?.id === leadId) {
          await loadDetailAttachments(leadId);
        }
        notifyAttachmentsChanged(leadId);
        showToast(
          newItems.length === 1
            ? "Attachment uploaded"
            : `${newItems.length} attachments uploaded`,
        );
      }

      setAttachUploading(false);
      if (attachFileInputRef.current) attachFileInputRef.current.value = "";
    },
    [detailLead?.id, loadDetailAttachments, showToast],
  );

  const handleViewFullProfile = async (leadId: string) => {
    setQuickActionLead(null);
    setConsultationLead(null);
    setAttachDropdownLeadId(null);
    setAttachDeleteConfirm(null);
    setIsLoadingDetail(true);
    setDetailLead(null);
    setDetailNotes([]);
    setDetailNewNote("");
    setDetailAttachments([]);
    try {
      const res = await leadsAPI.get(leadId);
      setDetailLead(res.data);
    } catch {
      showToast("Failed to load lead details", "error");
    } finally {
      setIsLoadingDetail(false);
    }
    // Load notes
    setDetailNotesLoading(true);
    try {
      const nr = await leadsAPI.getNotes(leadId);
      setDetailNotes(nr.data || []);
    } catch {
      setDetailNotes([]);
    } finally {
      setDetailNotesLoading(false);
    }
    loadDetailAttachments(leadId);
  };

  const handleOpenLeadEditor = useCallback(
    async (leadId: string) => {
      setIsOpeningEdit(true);
      try {
        const response = await leadsAPI.get(leadId);
        setEditLead(response.data);
        setDetailLead(null);
      } catch {
        showToast("Failed to load the latest lead data for editing", "error");
      } finally {
        setIsOpeningEdit(false);
      }
    },
    [showToast],
  );

  const handleSubmitDetailNote = async () => {
    if (!detailLead || !detailNewNote.trim()) return;
    try {
      const res = await leadsAPI.createNote(detailLead.id, {
        note_text: detailNewNote.trim(),
        note_type: "manual",
      });
      setDetailNotes((prev) => [res.data, ...prev]);
      setDetailNewNote("");
    } catch {
      showToast("Failed to add note", "error");
    }
  };

  const [deleteConfirmLead, setDeleteConfirmLead] = useState<Lead | null>(null);

  const handleDeleteLead = async (lead: Lead) => {
    setDeleteConfirmLead(lead);
  };

  const confirmDeleteLead = async () => {
    if (!deleteConfirmLead) return;
    try {
      await leadsAPI.delete(deleteConfirmLead.id);
      showToast(`Lead ${deleteConfirmLead.lead_number} deleted`);
      setDetailLead(null);
      setDeleteConfirmLead(null);
      setLeads((prev) => prev.filter((item) => item.id !== deleteConfirmLead.id));
    } catch {
      showToast("Failed to delete lead", "error");
    }
  };

  const handleDetailAttachmentUpload = useCallback(
    async (files: FileList | File[]) => {
      if (!detailLead?.id || !files.length) return;
      setDetailAttachmentUploading(true);
      let uploaded = 0;
      for (const file of Array.from(files)) {
        try {
          await uploadAttachment(detailLead.id, file);
          uploaded += 1;
        } catch {
          showToast(`Failed to upload ${file.name}`, "error");
        }
      }
      await loadDetailAttachments(detailLead.id);
      try {
        const counts = await getAttachmentCounts();
        setAttachmentCounts(counts);
      } catch {}
      if (uploaded > 0) {
        notifyAttachmentsChanged(detailLead.id);
        showToast(
          uploaded === 1
            ? "Attachment uploaded"
            : `${uploaded} attachments uploaded`,
        );
      }
      setDetailAttachmentUploading(false);
      if (detailAttachmentInputRef.current)
        detailAttachmentInputRef.current.value = "";
    },
    [detailLead?.id, loadDetailAttachments, showToast],
  );

  const handleDetailAttachmentDelete = useCallback(
    async (attachmentId: string) => {
      if (!detailLead?.id) return;
      setDetailAttachmentDeleting(attachmentId);
      try {
        await deleteAttachment(detailLead.id, attachmentId);
        setDetailAttachments((prev) =>
          prev.filter((item) => item.id !== attachmentId),
        );
        const counts = await getAttachmentCounts();
        setAttachmentCounts(counts);
        notifyAttachmentsChanged(detailLead.id);
        showToast("Attachment deleted");
      } catch {
        showToast("Failed to delete attachment", "error");
      } finally {
        setDetailAttachmentDeleting(null);
      }
    },
    [detailLead?.id, showToast],
  );

  const handleDetailAttachmentDownload = useCallback(
    async (attachment: Attachment) => {
      if (!detailLead?.id) return;
      try {
        await downloadAttachment(
          detailLead.id,
          attachment.id,
          attachment.filename,
        );
      } catch {
        showToast("Failed to download attachment", "error");
      }
    },
    [detailLead?.id, showToast],
  );

  // ── SMS Send ────────────────────────────────────────────────────────────
  const applySmsTemplate = (templateId: string, lead: Lead | null) => {
    const template = smsTemplates.find((item) => item.id === templateId);
    setSelectedSmsTemplate(templateId);
    setSmsMessage(personalizeTemplate(template?.message || "", lead));
  };

  const applyEmailTemplate = (templateId: string, lead: Lead | null) => {
    const template = emailTemplates.find((item) => item.id === templateId);
    setSelectedEmailTemplate(templateId);
    setEmailSubject(personalizeTemplate(template?.subject || "", lead));
    setEmailBody(personalizeTemplate(template?.body || "", lead));
  };

  const ensureTemplatesLoaded = useCallback(async (): Promise<{
    email: EmailTemplate[];
    sms: SMSTemplate[];
  }> => {
    if (templatesLoadedRef.current) {
      return { email: emailTemplates, sms: smsTemplates };
    }
    try {
      const res = await communicationsAPI.getTemplates();
      const email = res.data?.email_templates || [];
      const sms = res.data?.sms_templates || [];
      setEmailTemplates(email);
      setSmsTemplates(sms);
      templatesLoadedRef.current = true;
      return { email, sms };
    } catch {
      setEmailTemplates([]);
      setSmsTemplates([]);
      return { email: [], sms: [] };
    }
  }, [emailTemplates, smsTemplates]);

  const openSmsDialog = async (lead: Lead | null) => {
    const { sms } = await ensureTemplatesLoaded();
    setSmsDialogLead(lead);
    setSmsDialogOpen(true);
    const templateId = lead ? "follow_up" : "custom";
    const template = sms.find((item) => item.id === templateId);
    setSelectedSmsTemplate(templateId);
    setSmsMessage(personalizeTemplate(template?.message || "", lead));
  };

  const openEmailDialog = async (lead: Lead | null) => {
    const { email } = await ensureTemplatesLoaded();
    setEmailDialogLead(lead);
    setEmailDialogOpen(true);
    const templateId = lead ? "follow_up" : "custom";
    const template = email.find((item) => item.id === templateId);
    setSelectedEmailTemplate(templateId);
    setEmailSubject(personalizeTemplate(template?.subject || "", lead));
    setEmailBody(personalizeTemplate(template?.body || "", lead));
  };

  const handleSendSMS = async () => {
    if (!smsMessage.trim()) return;
    setSmsSending(true);
    try {
      const data: any = {
        category: selectedSmsTemplate || "custom",
        message: smsMessage.trim(),
      };
      if (smsDialogLead) data.lead_id = smsDialogLead.id;
      await communicationsAPI.sendSMS(data);
      showToast("SMS sent successfully");
      setSmsDialogOpen(false);
      setSmsMessage("");
      setSmsDialogLead(null);
      setSelectedSmsTemplate("custom");
    } catch {
      showToast("Failed to send SMS", "error");
    } finally {
      setSmsSending(false);
    }
  };

  const handleSendQuickSMS = useCallback(
    async (phone: string, message: string) => {
      await communicationsAPI.sendSMS({
        to_phone: phone,
        category: "custom",
        message,
      });
      showToast("SMS sent successfully");
      setQuickSmsOpen(false);
    },
    [showToast],
  );

  // ── Email Send ──────────────────────────────────────────────────────────
  const handleSendEmail = async () => {
    if (!emailSubject.trim() || !emailBody.trim() || !emailDialogLead) return;
    setEmailSending(true);
    try {
      await communicationsAPI.sendEmail({
        lead_id: emailDialogLead.id,
        category: selectedEmailTemplate || "custom",
        subject: emailSubject.trim(),
        body: emailBody.trim(),
      });
      showToast("Email sent successfully");
      setEmailDialogOpen(false);
      setEmailSubject("");
      setEmailBody("");
      setEmailDialogLead(null);
      setSelectedEmailTemplate("custom");
    } catch {
      showToast("Failed to send email", "error");
    } finally {
      setEmailSending(false);
    }
  };

  /* ═════════════════════════════════════════════════════════════════════════ */
  /* RENDER                                                                   */
  /* ═════════════════════════════════════════════════════════════════════════ */
  const PageIcon = pageMeta.icon;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden overscroll-none animate-fade-in">
      <div className="shrink-0 space-y-2 lg:space-y-3 px-0 pb-2 pt-1">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-gray-900">
              <PageIcon className="h-6 w-6 text-sleep-500" />
              {pageMeta.title}
            </h1>
            <p className="mt-1 text-[15px] text-gray-500">
              {pageMeta.subtitle}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSoundEnabled((v) => !v)}
              className={`p-2 rounded-lg transition-colors ${soundEnabled ? "text-sleep-600 hover:bg-sleep-50" : "text-gray-400 hover:bg-gray-100"}`}
              title={soundEnabled ? "Mute new lead notifications" : "Unmute new lead notifications"}
            >
              {soundEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
            </button>
          </div>
        </div>

        {/* KPI Cards — always single row, 4 cols */}
        <div className="grid grid-cols-4 gap-1.5 sm:gap-2 lg:gap-3">
          {kpis.map((card) => (
            <div
              key={card.label}
              className={`relative overflow-hidden rounded-lg lg:rounded-2xl p-2 sm:p-3 lg:p-4 bg-gradient-to-br ${card.gradient} text-white shadow-md`}
            >
              <div className="absolute top-0 right-0 h-16 w-16 translate-x-4 -translate-y-4 rounded-full bg-white/10 hidden lg:block" />
              <div className="relative z-10">
                <div className="mb-1 lg:mb-2 flex h-7 w-7 lg:h-9 lg:w-9 items-center justify-center rounded-lg bg-white/15">
                  <card.icon className="h-3.5 w-3.5 lg:h-4.5 lg:w-4.5 text-white" />
                </div>
                <p className="mb-0.5 text-[9px] sm:text-[10px] lg:text-xs font-medium uppercase tracking-wider text-white/70 truncate">
                  {card.label}
                </p>
                <p className="text-base sm:text-lg lg:text-2xl font-bold">{card.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Toolbar */}
        <div className="rounded-2xl border border-gray-100 bg-white shadow-sm">
          <div className="px-4 py-3">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-base font-bold text-gray-900">
                  {pageMeta.sectionTitle}
                </h2>
                <p className="text-xs text-gray-500">
                  {pageMeta.sectionSubtitle}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {/* Quick Call & SMS buttons */}
                <div className="flex items-center gap-1.5 border-r border-gray-200 pr-3">
                  <button
                    onClick={() => setQuickCallOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
                  >
                    <PhoneCall size={16} /> Call
                  </button>
                  <button
                    onClick={() => setQuickSmsOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                  >
                    <MessageSquare size={16} /> SMS
                  </button>
                  {activeQueue === "new" && (
                    <button
                      onClick={() => setShowManualLeadModal(true)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-gradient-to-r from-emerald-600 to-emerald-700 px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition-all hover:-translate-y-0.5 hover:from-emerald-700 hover:to-emerald-800"
                    >
                      <Plus size={16} />
                      Add Lead
                    </button>
                  )}
                </div>
                <span className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
                  {filteredLeads.length} of {leads.length} leads
                </span>
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg">
                  <Shield size={14} className="text-emerald-600" />
                  <span className="text-xs font-semibold text-emerald-700">
                    HIPAA Protected
                  </span>
                </div>
              </div>
            </div>

            {/* Filters + Search + Gear */}
            <div className="flex items-center justify-between gap-4 mt-3">
              <div className="flex items-center gap-2">
                <Filter size={14} className="text-gray-400" />
                <span className="text-sm text-gray-500 mr-1">
                  Quick filters:
                </span>
                {QUICK_FILTERS.map((f) => {
                  const isActive = activeFilter === f.key;
                  const activeBg = f.activeColor || "bg-sleep-600";
                  return (
                    <button
                      key={f.key}
                      onClick={() => setActiveFilter(f.key)}
                      className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${isActive ? `${activeBg} text-white shadow-md shadow-black/10` : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50 hover:border-gray-300"}`}
                    >
                      {f.icon && <f.icon size={13} className={isActive ? "text-white" : "text-gray-400"} />}
                      {f.key}
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search
                    size={14}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                  />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by name, email, phone..."
                    className="pl-9 pr-4 py-2 w-60 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sleep-500 focus:border-transparent placeholder:text-gray-400"
                  />
                  {search && (
                    <button
                      onClick={() => setSearch("")}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      ×
                    </button>
                  )}
                </div>
                {/* Task A: Column Visibility Settings Gear */}
                <div className="relative" ref={colToggleRef}>
                  <button
                    onClick={() => setShowColToggle((v) => !v)}
                    className="p-2 rounded-lg border border-gray-300 bg-white text-gray-500 hover:bg-gray-50 hover:text-gray-700 transition-colors"
                    title="Toggle column visibility"
                  >
                    <Settings size={16} />
                  </button>
                  {showColToggle && (
                    <div className="absolute right-0 top-11 z-[60] w-56 bg-white border border-gray-200 rounded-2xl shadow-2xl py-2.5 animate-fade-in">
                      <div className="flex items-center justify-between px-4 pb-2.5 mb-1 border-b border-gray-100">
                        <span className="text-xs font-bold text-gray-800 uppercase tracking-wider">
                          Columns
                        </span>
                        <button
                          onClick={() => setVisibleCols(new Set(COLUMN_KEYS))}
                          className="text-[11px] text-sleep-600 hover:text-sleep-800 font-semibold transition-colors"
                        >
                          Reset
                        </button>
                      </div>
                      {COLUMN_KEYS.map((col) => {
                        const isLocked = LOCKED_COLUMNS.includes(col);
                        return (
                          <label
                            key={col}
                            className={`flex items-center gap-3 px-4 py-2 ${isLocked ? "opacity-50 cursor-not-allowed" : "hover:bg-sleep-50/50 cursor-pointer"} transition-colors`}
                          >
                            <input
                              type="checkbox"
                              checked={visibleCols.has(col)}
                              disabled={isLocked}
                              onChange={(e) => {
                                if (isLocked) return;
                                setVisibleCols((prev) => {
                                  const n = new Set(prev);
                                  e.target.checked ? n.add(col) : n.delete(col);
                                  return n;
                                });
                              }}
                              className="w-4 h-4 rounded border-gray-300 text-sleep-600 focus:ring-sleep-500 disabled:opacity-50"
                            />
                            <span className="text-[13px] text-gray-700 font-medium flex items-center gap-1.5">
                              {COLUMN_LABELS[col]}
                              {isLocked && (
                                <span className="text-[9px] text-gray-400 bg-gray-100 px-1 py-0.5 rounded font-semibold">LOCKED</span>
                              )}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        {/* Table */}
        {isLoading ? (
          <div className="text-center py-16">
            <RefreshCw className="w-6 h-6 text-sleep-400 animate-spin mx-auto mb-3" />
            <p className="text-sm text-gray-400">Loading leads...</p>
          </div>
        ) : filteredLeads.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-sleep-50 border border-sleep-100 flex items-center justify-center mx-auto mb-4">
              <Inbox className="w-7 h-7 text-sleep-400" />
            </div>
            <h3 className="text-base font-semibold text-gray-900 mb-1">
              No leads in this queue
            </h3>
            <p className="text-sm text-gray-400">
              When new leads come in they will appear here.
            </p>
          </div>
        ) : (
          <div
            className="min-h-0 flex-1 overflow-auto overscroll-contain"
            style={{ scrollbarGutter: "stable both-edges" }}
          >
            <table className="w-full" style={{ minWidth: "1100px", tableLayout: "fixed" }}>
              {/* Column widths via <colgroup> — resizable */}
              <colgroup>
                {COLUMN_KEYS.filter((c) => visibleCols.has(c)).map((col) => (
                  <col key={col} style={{ width: colWidths[col] || 120 }} />
                ))}
              </colgroup>
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-gray-200 bg-gray-50">
                  {visibleCols.has("leadId") && (
                    <th
                      onClick={() => handleSort("leadId")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Lead ID {getSortIcon("leadId")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("leadId", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("patient") && (
                    <th
                      onClick={() => handleSort("firstName")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Patient {getSortIcon("firstName")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("patient", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("condition") && (
                    <th
                      onClick={() => handleSort("condition")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Condition {getSortIcon("condition")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("condition", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("priority") && (
                    <th
                      onClick={() => handleSort("priority")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Priority {getSortIcon("priority")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("priority", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("status") && (
                    <th
                      onClick={() => handleSort("status")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Status {getSortIcon("status")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("status", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("scheduledFor") && (
                    <th className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3">
                      Scheduled For
                      <div onMouseDown={(e) => handleResizeStart("scheduledFor", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("submitted") && (
                    <th
                      onClick={() => handleSort("submittedAt")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Submitted {getSortIcon("submittedAt")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("submitted", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("lastActivity") && (
                    <th
                      onClick={() => handleSort("lastUpdatedAt")}
                      className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 cursor-pointer hover:bg-gray-100"
                    >
                      <div className="flex items-center gap-1">
                        Last Activity {getSortIcon("lastUpdatedAt")}
                      </div>
                      <div onMouseDown={(e) => handleResizeStart("lastActivity", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("preferred") && (
                    <th className="relative text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-3">
                      Preferred
                      <div onMouseDown={(e) => handleResizeStart("preferred", e)} className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-sleep-400 active:bg-sleep-500" />
                    </th>
                  )}
                  {visibleCols.has("actions") && (
                    <th className="text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {paginatedLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    className="group border-t border-gray-50 transition-colors duration-100 hover:bg-sleep-50/30"
                  >
                    {visibleCols.has("leadId") && (
                      <td className="px-5 py-3 whitespace-nowrap">
                        <span className="text-xs font-mono font-semibold text-sleep-600">
                          {lead.lead_number || "—"}
                        </span>
                      </td>
                    )}
                    {visibleCols.has("patient") && (
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sleep-100 to-sleep-200 flex items-center justify-center flex-shrink-0">
                            <span className="text-xs font-semibold text-sleep-700">
                              {(lead.first_name || "?").charAt(0)}
                              {(lead.last_name || "").charAt(0)}
                            </span>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              {lead.first_name} {lead.last_name || ""}
                            </p>
                            {lead.is_referral && (
                              <span className="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded-full font-medium">
                                {lead.referring_provider_name
                                  ? `Ref: ${lead.referring_provider_name}`
                                  : "Referral"}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                    )}
                    {visibleCols.has("condition") && (
                      <td className="px-4 py-3 overflow-hidden">
                        <span
                          className="text-sm text-gray-600 capitalize block overflow-hidden text-ellipsis whitespace-nowrap"
                          title={conditionLabel(lead)}
                        >
                          {conditionLabel(lead)}
                        </span>
                      </td>
                    )}
                    {visibleCols.has("priority") && (
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${priorityBadge(lead.priority)}`}
                        >
                          {lead.priority}
                        </span>
                      </td>
                    )}
                    {visibleCols.has("status") && (
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${statusBadge(lead.status)}`}
                          >
                            {lead.status?.replace(/_/g, " ")}
                          </span>
                          {lead.follow_up_reason && (
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-px text-[9px] font-medium rounded bg-indigo-50 text-indigo-600 border border-indigo-100 w-fit mt-0.5">
                              <Tag size={7} />
                              {lead.follow_up_reason}
                            </span>
                          )}
                        </div>
                      </td>
                    )}
                    {visibleCols.has("scheduledFor") && (
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {lead.scheduled_callback_at
                          ? formatDate(lead.scheduled_callback_at)
                          : "—"}
                      </td>
                    )}
                    {visibleCols.has("submitted") && (
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {formatDate(lead.created_at)}
                      </td>
                    )}
                    {visibleCols.has("lastActivity") && (
                      <td className="px-4 py-3">
                        {lead.last_updated_at ? (
                          <span className="text-sm text-gray-700 font-medium">
                            {timeAgo(lead.last_updated_at)}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                            New
                          </span>
                        )}
                      </td>
                    )}
                    {visibleCols.has("preferred") && (
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {formatPreferred(lead.preferred_contact_method)}
                      </td>
                    )}
                    {/* Task B: Action Icons — always visible */}
                    {visibleCols.has("actions") && (
                      <td className="px-5 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {lead.phone && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCallVia3CX(lead.phone!);
                              }}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                              title={`Call ${lead.first_name} via 3CX`}
                            >
                              <PhoneCall size={15} />
                            </button>
                          )}
                          {lead.phone && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openSmsDialog(lead);
                              }}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                              title={`SMS ${lead.first_name}`}
                            >
                              <MessageSquare size={15} />
                            </button>
                          )}
                          {lead.email && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openEmailDialog(lead);
                              }}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title={`Email ${lead.first_name}`}
                            >
                              <Mail size={15} />
                            </button>
                          )}
                          {(attachmentCounts[lead.id] || 0) > 0 && (
                            <div className="relative">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openAttachDropdown(lead.id, e.currentTarget);
                                }}
                                className={`relative rounded-lg p-1.5 transition-colors ${attachDropdownLeadId === lead.id ? "bg-amber-50 text-amber-600" : "text-amber-500 hover:bg-amber-50 hover:text-amber-600"}`}
                                title={`${attachmentCounts[lead.id]} attachment${attachmentCounts[lead.id] === 1 ? "" : "s"}`}
                              >
                                <Paperclip size={15} />
                                <span className="absolute -right-0.5 -top-0.5 inline-flex min-h-[16px] min-w-[16px] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-bold text-white">
                                  {attachmentCounts[lead.id]}
                                </span>
                              </button>

                              {attachDropdownLeadId === lead.id && (
                                <div
                                  ref={attachDropdownRef}
                                  className={`absolute right-0 z-50 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl ${attachDropdownPlacement === "up" ? "bottom-full mb-1 origin-bottom-right" : "top-full mt-1 origin-top-right"}`}
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  <div className="flex items-center justify-between border-b border-amber-100 bg-gradient-to-r from-amber-50 to-orange-50 px-3.5 py-2.5">
                                    <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
                                      <Paperclip size={12} />
                                      Attachments (
                                      {attachmentCounts[lead.id] ||
                                        attachDropdownItems.length}
                                      )
                                    </span>
                                    <button
                                      onClick={() => {
                                        setAttachDropdownLeadId(null);
                                        setAttachDeleteConfirm(null);
                                      }}
                                      className="text-sm font-medium text-amber-400 hover:text-amber-600"
                                    >
                                      ×
                                    </button>
                                  </div>

                                  {attachDropdownLoading ? (
                                    <div className="flex items-center justify-center py-6">
                                      <Loader2
                                        size={18}
                                        className="animate-spin text-amber-500"
                                      />
                                      <span className="ml-2 text-xs text-gray-500">
                                        Loading attachments...
                                      </span>
                                    </div>
                                  ) : attachDropdownItems.length > 0 ? (
                                    <div className="max-h-56 overflow-y-auto divide-y divide-gray-50">
                                      {attachDropdownItems.map((attachment) => (
                                        <div key={attachment.id}>
                                          {attachDeleteConfirm ===
                                          attachment.id ? (
                                            <div className="flex items-center justify-between border-l-2 border-red-400 bg-red-50 px-3.5 py-2.5">
                                              <span className="text-[11px] font-medium text-red-700">
                                                Delete this file?
                                              </span>
                                              <div className="flex items-center gap-1.5">
                                                <button
                                                  onClick={() =>
                                                    setAttachDeleteConfirm(null)
                                                  }
                                                  className="rounded border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-medium text-gray-600 transition-colors hover:bg-gray-50"
                                                >
                                                  Cancel
                                                </button>
                                                <button
                                                  onClick={() =>
                                                    handleAttachmentDelete(
                                                      lead.id,
                                                      attachment.id,
                                                    )
                                                  }
                                                  disabled={
                                                    attachDeleting ===
                                                    attachment.id
                                                  }
                                                  className="flex items-center gap-1 rounded bg-red-600 px-2 py-0.5 text-[10px] font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
                                                >
                                                  {attachDeleting ===
                                                  attachment.id ? (
                                                    <Loader2
                                                      size={10}
                                                      className="animate-spin"
                                                    />
                                                  ) : (
                                                    <Trash2 size={10} />
                                                  )}
                                                  Delete
                                                </button>
                                              </div>
                                            </div>
                                          ) : (
                                            <div className="group/item flex items-center gap-2 px-3.5 py-2 transition-colors hover:bg-gray-50/80">
                                              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100">
                                                {getAttachmentIcon(
                                                  attachment.file_type,
                                                )}
                                              </div>
                                              <div className="min-w-0 flex-1">
                                                <p
                                                  className="truncate text-xs font-medium text-gray-800"
                                                  title={attachment.filename}
                                                >
                                                  {attachment.filename}
                                                </p>
                                                <p className="text-[10px] text-gray-400">
                                                  {formatFileSize(
                                                    attachment.file_size,
                                                  )}{" "}
                                                  ·{" "}
                                                  {new Date(
                                                    attachment.created_at,
                                                  ).toLocaleDateString(
                                                    "en-US",
                                                    {
                                                      month: "short",
                                                      day: "numeric",
                                                    },
                                                  )}
                                                </p>
                                              </div>
                                              <div className="flex flex-shrink-0 items-center gap-0.5">
                                                <button
                                                  onClick={(event) => {
                                                    event.stopPropagation();
                                                    handleAttachmentDownload(
                                                      lead.id,
                                                      attachment,
                                                    );
                                                  }}
                                                  disabled={
                                                    attachDownloading ===
                                                    attachment.id
                                                  }
                                                  className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-blue-50 hover:text-blue-600 disabled:opacity-50"
                                                  title={`Download ${attachment.filename}`}
                                                >
                                                  {attachDownloading ===
                                                  attachment.id ? (
                                                    <Loader2
                                                      size={13}
                                                      className="animate-spin"
                                                    />
                                                  ) : (
                                                    <Download size={13} />
                                                  )}
                                                </button>
                                                <button
                                                  onClick={(event) => {
                                                    event.stopPropagation();
                                                    setAttachDeleteConfirm(
                                                      attachment.id,
                                                    );
                                                  }}
                                                  className="rounded-lg p-1.5 text-gray-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-600 group-hover/item:opacity-100"
                                                  title={`Delete ${attachment.filename}`}
                                                >
                                                  <Trash2 size={13} />
                                                </button>
                                              </div>
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <div className="py-6 text-center">
                                      <Paperclip
                                        size={20}
                                        className="mx-auto mb-1 text-gray-300"
                                      />
                                      <p className="text-xs text-gray-400">
                                        No attachments found
                                      </p>
                                    </div>
                                  )}

                                  {!attachDropdownLoading && (
                                    <div className="border-t border-gray-100 bg-gray-50/50 px-3.5 py-2.5">
                                      <input
                                        ref={attachFileInputRef}
                                        type="file"
                                        multiple
                                        accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.webp"
                                        className="hidden"
                                        onChange={(event) => {
                                          if (
                                            event.target.files &&
                                            event.target.files.length > 0
                                          ) {
                                            handleAttachmentUploadMore(
                                              lead.id,
                                              event.target.files,
                                            );
                                          }
                                        }}
                                      />
                                      <button
                                        onClick={() =>
                                          attachFileInputRef.current?.click()
                                        }
                                        disabled={attachUploading}
                                        className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-all hover:border-amber-300 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {attachUploading ? (
                                          <>
                                            <Loader2
                                              size={12}
                                              className="animate-spin"
                                            />
                                            Uploading...
                                          </>
                                        ) : (
                                          <>
                                            <Plus size={12} />
                                            Upload More Documents
                                          </>
                                        )}
                                      </button>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                          <button
                            onClick={() => handleOpenInteractionPanel(lead)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                            title="Open interaction panel"
                          >
                            <Eye size={15} />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        {!isLoading && filteredLeads.length > 0 && (
          <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
            <span>
              Showing {(tablePage - 1) * PAGE_SIZE + 1}–
              {Math.min(tablePage * PAGE_SIZE, filteredLeads.length)} of{" "}
              {filteredLeads.length} leads
              {" "}&middot;{" "}
              <span className="text-gray-400">Sorted: {sortField} ({sortDir})</span>
            </span>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setTablePage((p) => Math.max(1, p - 1))}
                  disabled={tablePage <= 1}
                  className="p-1.5 rounded-lg border border-gray-300 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-40"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="text-xs text-gray-600 px-2 font-medium">
                  Page {tablePage} of {totalPages}
                </span>
                <button
                  onClick={() =>
                    setTablePage((p) => Math.min(totalPages, p + 1))
                  }
                  disabled={tablePage >= totalPages}
                  className="p-1.5 rounded-lg border border-gray-300 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-40"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* QUICK ACTION PANEL (Task C — for non-scheduled leads)          */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {quickActionLead && (
        <QuickActionPanel
          lead={quickActionLead}
          onClose={() => {
            setQuickActionLead(null);
          }}
          onViewDetails={handleViewFullProfile}
          showToast={showToast}
          onLeadUpdated={mergeLeadIntoState}
          onOutcomeRecorded={(leadId: string) => {
            setQuickActionLead(null);
            handleOutcomeRecorded(leadId);
          }}
        />
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* CONSULTATION PANEL (Task C — for scheduled leads)              */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {consultationLead && (
        <ConsultationPanel
          lead={consultationLead}
          onClose={() => {
            setConsultationLead(null);
          }}
          onViewDetails={handleViewFullProfile}
          showToast={showToast}
          onLeadUpdated={mergeLeadIntoState}
          onOutcomeRecorded={(leadId: string) => {
            setConsultationLead(null);
            handleOutcomeRecorded(leadId);
          }}
        />
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* LEAD DETAIL MODAL (Task C — View Full Profile)                 */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {(detailLead || isLoadingDetail) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => {
            setDetailLead(null);
            setIsLoadingDetail(false);
          }}
        >
          <div
            className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl m-4"
            onClick={(e) => e.stopPropagation()}
          >
            {isLoadingDetail && !detailLead ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-sleep-500" />
              </div>
            ) : detailLead ? (
              <>
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                  <div>
                    <h3 className="text-xl font-bold text-gray-900">
                      {detailLead.first_name} {detailLead.last_name || ""}
                    </h3>
                    <p className="text-sm text-gray-500 font-mono">
                      {detailLead.lead_number}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${priorityBadge(detailLead.priority)}`}
                    >
                      {detailLead.priority}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${statusBadge(detailLead.status)}`}
                    >
                      {detailLead.status?.replace(/_/g, " ")}
                    </span>
                    <button
                      onClick={() => {
                        setDetailLead(null);
                        setIsLoadingDetail(false);
                      }}
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <X size={20} />
                    </button>
                  </div>
                </div>
                <div className="px-6 py-4 space-y-5">
                  {/* Lead Score */}
                  {detailLead.score != null && (
                    <div className="rounded-lg p-3 bg-gray-50 border border-gray-200">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-600">
                          Lead Score
                        </span>
                        <span className="text-xl font-bold text-gray-900">
                          {detailLead.score}
                        </span>
                      </div>
                    </div>
                  )}
                  {/* Contact Info */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                      <Mail size={16} className="text-gray-400" />
                      <div>
                        <p className="text-xs text-gray-500">Email</p>
                        <p className="text-sm text-blue-600">
                          {detailLead.email || "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                      <Phone size={16} className="text-gray-400" />
                      <div>
                        <p className="text-xs text-gray-500">Phone</p>
                        <p className="text-sm text-blue-600">
                          {detailLead.phone || "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                      <MapPin size={16} className="text-gray-400" />
                      <div>
                        <p className="text-xs text-gray-500">ZIP Code</p>
                        <p className="text-sm text-gray-900">
                          {detailLead.zip_code || "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
                      <Calendar size={16} className="text-gray-400" />
                      <div>
                        <p className="text-xs text-gray-500">Submitted</p>
                        <p className="text-sm text-gray-900">
                          {formatDate(detailLead.created_at)}
                        </p>
                      </div>
                    </div>
                  </div>
                  {/* Clinical Info */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Clinical Information
                    </h4>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <span className="text-gray-500">Condition:</span>{" "}
                        <span className="text-gray-900 capitalize">
                          {conditionLabel(detailLead)}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Duration:</span>{" "}
                        <span className="text-gray-900">
                          {detailLead.symptom_duration?.replace(/_/g, " ") ||
                            "—"}
                        </span>
                      </div>
                      {detailLead.sleep_treatment_interest && (
                        <div>
                          <span className="text-gray-500">
                            Treatment Interest:
                          </span>{" "}
                          <span className="text-gray-900">
                            {treatmentInterestLabel(
                              detailLead.sleep_treatment_interest,
                            )}
                          </span>
                        </div>
                      )}
                      {detailLead.urgency && (
                        <div>
                          <span className="text-gray-500">Urgency:</span>{" "}
                          <span className="text-gray-900">
                            {detailLead.urgency.replace(/_/g, " ")}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Insurance */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Insurance
                    </h4>
                    <p className="text-sm text-gray-900">
                      {detailLead.has_insurance
                        ? `✓ ${detailLead.insurance_provider || "Provider not specified"}`
                        : "No insurance / Self-pay"}
                    </p>
                  </div>
                  {detailLead.is_referral && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 mb-2">
                        Referral
                      </h4>
                      <p className="text-sm text-gray-900">
                        {detailLead.referring_provider_name
                          ? `Ref: ${detailLead.referring_provider_name}`
                          : "Referral lead"}
                      </p>
                    </div>
                  )}
                  {/* Attachments */}
                  <div>
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                        <Paperclip size={14} className="text-gray-500" />{" "}
                        Attachments
                      </h4>
                      <div className="flex items-center gap-2">
                        <input
                          ref={detailAttachmentInputRef}
                          type="file"
                          multiple
                          className="hidden"
                          onChange={(e) =>
                            e.target.files &&
                            handleDetailAttachmentUpload(e.target.files)
                          }
                          accept=".pdf,.doc,.docx,.xls,.xlsx,.jpeg,.jpg,.png,.gif,.webp,.bmp,.tiff"
                        />
                        <button
                          onClick={() =>
                            detailAttachmentInputRef.current?.click()
                          }
                          disabled={detailAttachmentUploading}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                        >
                          {detailAttachmentUploading ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Upload size={13} />
                          )}
                          Upload
                        </button>
                      </div>
                    </div>
                    <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50/60 p-3 text-center text-xs text-gray-500">
                      Drag files onto this window or use Upload. Referral faxes,
                      PDFs, spreadsheets, and images are supported up to 25MB
                      each.
                    </div>
                    <div
                      className="mt-3"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        if (event.dataTransfer.files?.length)
                          handleDetailAttachmentUpload(
                            event.dataTransfer.files,
                          );
                      }}
                    >
                      {detailAttachmentsLoading ? (
                        <div className="flex items-center py-4">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin text-gray-400" />
                          <span className="text-sm text-gray-500">
                            Loading attachments...
                          </span>
                        </div>
                      ) : detailAttachments.length === 0 ? (
                        <p className="text-sm text-gray-400 italic">
                          No attachments yet
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {detailAttachments.map((attachment) => (
                            <div
                              key={attachment.id}
                              className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3"
                            >
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium text-gray-900">
                                  {attachment.filename}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {attachmentTypeLabel(attachment.file_type)} ·{" "}
                                  {formatFileSize(attachment.file_size)} ·{" "}
                                  {noteTimeAgo(attachment.created_at)}
                                </p>
                              </div>
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() =>
                                    handleDetailAttachmentDownload(attachment)
                                  }
                                  className="rounded-lg p-2 text-gray-400 hover:bg-blue-50 hover:text-blue-600"
                                  title="Download attachment"
                                >
                                  <Download size={15} />
                                </button>
                                <button
                                  onClick={() =>
                                    handleDetailAttachmentDelete(attachment.id)
                                  }
                                  disabled={
                                    detailAttachmentDeleting === attachment.id
                                  }
                                  className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                                  title="Delete attachment"
                                >
                                  {detailAttachmentDeleting ===
                                  attachment.id ? (
                                    <Loader2
                                      size={15}
                                      className="animate-spin"
                                    />
                                  ) : (
                                    <Trash2 size={15} />
                                  )}
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Attribution */}
                  {(detailLead.utm_source || detailLead.utm_medium) && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 mb-2">
                        Attribution
                      </h4>
                      <div className="flex gap-2 text-xs">
                        {detailLead.utm_source && (
                          <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded">
                            Source: {detailLead.utm_source}
                          </span>
                        )}
                        {detailLead.utm_medium && (
                          <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded">
                            Medium: {detailLead.utm_medium}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                  {/* Notes */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                      <FileText size={14} className="text-gray-500" /> Notes
                    </h4>
                    <div className="flex gap-2 mb-3">
                      <textarea
                        value={detailNewNote}
                        onChange={(e) => setDetailNewNote(e.target.value)}
                        placeholder="Add a note..."
                        rows={2}
                        className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-sleep-500"
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                            handleSubmitDetailNote();
                        }}
                      />
                      <button
                        onClick={handleSubmitDetailNote}
                        disabled={!detailNewNote.trim()}
                        className="self-end px-3 py-2 bg-sleep-600 text-white rounded-lg hover:bg-sleep-700 disabled:opacity-50"
                      >
                        <Send size={16} />
                      </button>
                    </div>
                    <p className="text-[10px] text-gray-400 mb-2">
                      Press Ctrl+Enter to submit
                    </p>
                    {detailNotesLoading ? (
                      <div className="flex items-center py-4">
                        <Loader2 className="w-4 h-4 animate-spin text-gray-400 mr-2" />
                        <span className="text-sm text-gray-500">
                          Loading notes...
                        </span>
                      </div>
                    ) : detailNotes.length === 0 ? (
                      <p className="text-sm text-gray-400 italic">
                        No notes yet
                      </p>
                    ) : (
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {detailNotes.map((note) => (
                          <div
                            key={note.id}
                            className="border border-gray-100 rounded-lg p-3 bg-gray-50/50"
                          >
                            <div className="flex items-center justify-between mb-1.5">
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center">
                                  <User size={12} className="text-blue-600" />
                                </div>
                                <span className="text-xs font-medium text-gray-700">
                                  {note.created_by_name || "System"}
                                </span>
                                {note.note_type === "outcome" &&
                                  note.related_outcome && (
                                    <span className="px-1.5 py-0.5 text-[10px] font-medium bg-indigo-100 text-indigo-700 rounded">
                                      {note.related_outcome.replace(/_/g, " ")}
                                    </span>
                                  )}
                                {note.note_type === "system" && (
                                  <span className="px-1.5 py-0.5 text-[10px] font-medium bg-gray-200 text-gray-600 rounded">
                                    Auto
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-1 text-[10px] text-gray-400">
                                <Clock size={10} />
                                {noteTimeAgo(note.created_at)}
                              </div>
                            </div>
                            <p className="text-sm text-gray-700 whitespace-pre-wrap">
                              {note.note_text}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200">
                  <button
                    onClick={() => {
                      setDetailLead(null);
                      setIsLoadingDetail(false);
                    }}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                  >
                    <X size={15} /> Close
                  </button>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleOpenLeadEditor(detailLead.id)}
                      disabled={isOpeningEdit}
                      className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isOpeningEdit ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Edit2 size={15} />
                      )}
                      Edit Lead
                    </button>
                    {isAdmin && (
                      <button
                        onClick={() => handleDeleteLead(detailLead)}
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100"
                      >
                        <Trash2 size={15} /> Delete Lead
                      </button>
                    )}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}

      <ManualLeadModal
        isOpen={showManualLeadModal}
        onClose={() => setShowManualLeadModal(false)}
        onSuccess={(leadNumber) => {
          setShowManualLeadModal(false);
          fetchLeads();
          showToast(`${leadNumber} created successfully`);
        }}
      />

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* DELETE CONFIRMATION MODAL                                       */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {deleteConfirmLead && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={() => setDeleteConfirmLead(null)}>
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-100">
                <Trash2 className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <h3 className="font-bold text-gray-900">Delete lead?</h3>
                <p className="text-sm text-gray-500">{deleteConfirmLead.lead_number}</p>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-5">This will soft-delete the lead. It can be restored from Deleted Leads.</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirmLead(null)} className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 rounded-xl hover:bg-gray-200">Cancel</button>
              <button onClick={confirmDeleteLead} className="px-4 py-2 text-sm font-semibold text-white bg-red-600 rounded-xl hover:bg-red-700">Delete Lead</button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* EDIT LEAD MODAL                                                */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      <LeadEditModal
        isOpen={Boolean(editLead)}
        lead={editLead}
        onClose={() => setEditLead(null)}
        onSave={(updatedLead) => {
          mergeLeadIntoState(updatedLead as Lead);
          setEditLead(null);
          showToast("Lead updated");
        }}
      />

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* SMS COMPOSE DIALOG                                             */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      <PhoneDialModal
        isOpen={quickCallOpen}
        onClose={() => setQuickCallOpen(false)}
        onCall={handleCallVia3CX}
      />

      <QuickSMSModal
        isOpen={quickSmsOpen}
        onClose={() => setQuickSmsOpen(false)}
        onSend={handleSendQuickSMS}
      />

      {smsDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setSmsDialogOpen(false)}
        >
          <div
            className="bg-white rounded-2xl w-full max-w-md shadow-2xl m-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                <MessageSquare size={20} className="text-emerald-600" /> Send
                SMS
              </h3>
              <button
                onClick={() => setSmsDialogOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            {smsDialogLead ? (
              <p className="text-sm text-gray-500 mb-4">
                To: {smsDialogLead.first_name} {smsDialogLead.last_name || ""}{" "}
                &lt;{smsDialogLead.phone}&gt;
              </p>
            ) : (
              <p className="text-sm text-gray-500 mb-4">Quick SMS composer</p>
            )}
            <div className="mb-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Templates
              </p>
              <div className="flex flex-wrap gap-2">
                {smsTemplates
                  .filter((template) => template.id !== "lead_receipt")
                  .map((template) => (
                    <button
                      key={template.id}
                      onClick={() =>
                        applySmsTemplate(template.id, smsDialogLead)
                      }
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${selectedSmsTemplate === template.id ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"}`}
                    >
                      {template.label}
                    </button>
                  ))}
              </div>
            </div>
            <textarea
              value={smsMessage}
              onChange={(e) => setSmsMessage(e.target.value)}
              placeholder="Type your message..."
              rows={5}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-sleep-500 mb-2"
            />
            <p className="text-xs text-gray-400 mb-4">
              {smsMessage.length} characters
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setSmsDialogOpen(false)}
                className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleSendSMS}
                disabled={smsSending || !smsMessage.trim()}
                className="px-4 py-2 text-sm text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-2"
              >
                {smsSending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Send size={16} />
                )}{" "}
                Send SMS
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* EMAIL COMPOSE DIALOG                                           */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {emailDialogOpen && emailDialogLead && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setEmailDialogOpen(false)}
        >
          <div
            className="bg-white rounded-2xl w-full max-w-lg shadow-2xl m-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                <Mail size={20} className="text-blue-600" /> Send Email
              </h3>
              <button
                onClick={() => setEmailDialogOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              To: {emailDialogLead.first_name} {emailDialogLead.last_name || ""}{" "}
              &lt;{emailDialogLead.email}&gt;
            </p>
            <div className="mb-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Templates
              </p>
              <div className="flex flex-wrap gap-2">
                {emailTemplates
                  .filter((template) => template.id !== "lead_receipt")
                  .map((template) => (
                    <button
                      key={template.id}
                      onClick={() =>
                        applyEmailTemplate(template.id, emailDialogLead)
                      }
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${selectedEmailTemplate === template.id ? "bg-blue-50 text-blue-700 border-blue-200" : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"}`}
                    >
                      {template.label}
                    </button>
                  ))}
              </div>
            </div>
            <input
              type="text"
              value={emailSubject}
              onChange={(e) => setEmailSubject(e.target.value)}
              placeholder="Subject"
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg mb-3 focus:outline-none focus:ring-2 focus:ring-sleep-500"
            />
            <textarea
              value={emailBody}
              onChange={(e) => setEmailBody(e.target.value)}
              placeholder="Email body..."
              rows={8}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-sleep-500 mb-2"
            />
            <p className="text-xs text-gray-400 mb-4">
              Templates are editable before sending.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setEmailDialogOpen(false)}
                className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleSendEmail}
                disabled={
                  emailSending || !emailSubject.trim() || !emailBody.trim()
                }
                className="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
              >
                {emailSending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Send size={16} />
                )}{" "}
                Send Email
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* TOAST CONTAINER                                                */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={`flex items-center gap-3 px-5 py-3 rounded-xl shadow-lg ${t.type === "success" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"}`}
            >
              {t.type === "success" ? (
                <CheckCircle2 size={18} />
              ) : (
                <X size={18} />
              )}
              <span className="text-sm font-medium max-w-xs">{t.message}</span>
              <button
                onClick={() =>
                  setToasts((prev) => prev.filter((x) => x.id !== t.id))
                }
                className="ml-2 opacity-80 hover:opacity-100"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* QUICK ACTION PANEL COMPONENT                                              */
/* Replicates NeuroReach QuickActionPanel — for non-scheduled leads          */
/* ═══════════════════════════════════════════════════════════════════════════ */
function QuickActionPanel({
  lead,
  onClose,
  onViewDetails,
  showToast,
  onLeadUpdated,
  onOutcomeRecorded,
}: {
  lead: Lead;
  onClose: () => void;
  onViewDetails: (id: string) => void;
  showToast: (msg: string, type?: "success" | "error") => void;
  onLeadUpdated: (updatedLead: Partial<Lead> & { id: string }) => void;
  onOutcomeRecorded: (leadId: string) => void;
}) {
  type View =
    | "actions"
    | "confirmation"
    | "schedule_consultation"
    | "schedule_callback";
  const [view, setView] = useState<View>("actions");
  const [pendingOutcome, setPendingOutcome] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [schedDate, setSchedDate] = useState("");
  const [schedTime, setSchedTime] = useState("");
  const [schedError, setSchedError] = useState<string | null>(null);

  // Draggable panel state
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setDragOffset({ x: 0, y: 0 });
  }, [lead.id]);

  const handleDragStart = (e: React.MouseEvent) => {
    isDragging.current = true;
    dragStart.current = {
      x: e.clientX - dragOffset.x,
      y: e.clientY - dragOffset.y,
    };
    const onMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      setDragOffset({
        x: ev.clientX - dragStart.current.x,
        y: ev.clientY - dragStart.current.y,
      });
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (view !== "actions") {
          setView("actions");
          setPendingOutcome(null);
        } else onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [view, onClose]);

  const currentOutcome = lead.contact_outcome || "NEW";
  const cfg =
    CONTACT_OUTCOME_CONFIG[currentOutcome] || CONTACT_OUTCOME_CONFIG.NEW;

  const openScheduleView = (
    v: "schedule_consultation" | "schedule_callback",
  ) => {
    const tmrw = new Date();
    tmrw.setDate(tmrw.getDate() + 1);
    setSchedDate(tmrw.toISOString().split("T")[0]);
    const nh = new Date();
    nh.setHours(nh.getHours() + 1, 0, 0, 0);
    setSchedTime(nh.toTimeString().slice(0, 5));
    setSchedError(null);
    setView(v);
  };

  const handleConfirm = async () => {
    if (!pendingOutcome || isUpdating) return;
    setIsUpdating(true);
    try {
      await leadsAPI.updateContactOutcome(lead.id, {
        contact_outcome: pendingOutcome,
        notes: noteText.trim() || undefined,
      });
      const name = `${lead.first_name} ${lead.last_name || ""}`.trim();
      const msgs: Record<string, string> = {
        ANSWERED: `✓ ${name} moved to Contacted`,
        NO_ANSWER: `✓ ${name} → Follow-up (No Answer)`,
        UNREACHABLE: `✓ ${name} → Unreachable`,
        NOT_INTERESTED: `✓ ${name} → Follow-up (Not Interested)`,
      };
      showToast(msgs[pendingOutcome] || `✓ ${name} outcome updated`);
      // Remove lead from current queue and refetch — prevents ghost rows
      onOutcomeRecorded(lead.id);
    } catch {
      showToast("Failed to update outcome", "error");
      setView("confirmation");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleScheduleSubmit = async (type: "consultation" | "callback") => {
    if (isUpdating) return;
    if (!schedDate || !schedTime) {
      setSchedError("Please select both date and time");
      return;
    }
    const dt = new Date(`${schedDate}T${schedTime}`);
    if (dt < new Date()) {
      setSchedError("Cannot schedule in the past");
      return;
    }
    setIsUpdating(true);
    try {
      await leadsAPI.schedule(lead.id, {
        scheduled_callback_at: dt.toISOString(),
        contact_method: "PHONE",
        schedule_type: type,
        scheduled_notes: noteText.trim() || undefined,
      });
      if (noteText.trim()) {
        try {
          await leadsAPI.createNote(lead.id, {
            note_text: noteText.trim(),
            note_type: "manual",
          });
        } catch {}
      }
      const name = `${lead.first_name} ${lead.last_name || ""}`.trim();
      const dateStr = dt.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
      showToast(
        type === "consultation"
          ? `✓ Consultation scheduled for ${name} on ${dateStr}`
          : `✓ Callback scheduled for ${name} on ${dateStr}`,
      );
      // Remove from current queue and refetch — lead moved to Scheduled/Callback
      onOutcomeRecorded(lead.id);
    } catch (err: any) {
      setSchedError(err?.response?.data?.detail || "Failed to schedule");
      showToast("Failed to schedule", "error");
    } finally {
      setIsUpdating(false);
    }
  };

  const OUTCOMES = [
    {
      key: "ANSWERED",
      label: "Answered",
      icon: <CheckCircle2 size={18} className="text-emerald-500" />,
      color: "text-emerald-700",
      bg: "bg-emerald-50",
      border: "border-emerald-200",
      desc: "Lead → Contacted queue",
    },
    {
      key: "NO_ANSWER",
      label: "No Answer",
      icon: <PhoneMissed size={18} className="text-amber-500" />,
      color: "text-amber-700",
      bg: "bg-amber-50",
      border: "border-amber-200",
      desc: "Lead → Follow-up queue",
    },
    {
      key: "UNREACHABLE",
      label: "Unreachable",
      icon: <PhoneOff size={18} className="text-red-500" />,
      color: "text-red-700",
      bg: "bg-red-50",
      border: "border-red-200",
      desc: "Lead → Unreachable queue",
    },
    {
      key: "NOT_INTERESTED",
      label: "Not Interested",
      icon: <Ban size={18} className="text-slate-500" />,
      color: "text-slate-700",
      bg: "bg-slate-100",
      border: "border-slate-300",
      desc: "Lead → Follow-up queue (+14d)",
    },
  ];

  return (
    <>
      <div className="fixed inset-0 bg-black/5 z-40 pointer-events-none" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="pointer-events-auto w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden"
          style={{ transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` }}
        >
          {/* Header — drag handle */}
          <div
            className="relative bg-gradient-to-r from-slate-800 to-slate-900 text-white px-5 py-4 cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleDragStart}
          >
            <button
              onClick={onClose}
              className="absolute top-3 right-3 p-1.5 hover:bg-white/10 rounded-lg"
            >
              <X size={18} />
            </button>
            <div className="flex items-center gap-3">
              <div
                className={`w-12 h-12 rounded-xl flex items-center justify-center ${lead.priority === "HOT" ? "bg-red-500/20" : lead.priority === "MEDIUM" ? "bg-amber-500/20" : "bg-slate-500/20"}`}
              >
                {lead.priority === "HOT" ? (
                  <Flame size={24} className="text-red-400" />
                ) : lead.priority === "MEDIUM" ? (
                  <Zap size={24} className="text-amber-400" />
                ) : (
                  <User size={24} className="text-slate-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-lg leading-tight truncate">
                  {lead.first_name} {lead.last_name || ""}
                </h3>
                <p className="text-slate-300 text-sm truncate uppercase">
                  {conditionLabel(lead)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3">
              <span className="text-xs font-mono text-slate-400 bg-slate-700/50 px-2 py-1 rounded">
                {lead.lead_number}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${priorityBadge(lead.priority)}`}
              >
                {lead.priority}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${statusBadge(lead.status)}`}
              >
                {lead.status?.replace(/_/g, " ")}
              </span>
            </div>
          </div>

          {/* Status Banner */}
          <div
            className={`px-5 py-3 flex items-center justify-between ${cfg.bgColor} border-b ${cfg.borderColor}`}
          >
            <div className="flex items-center gap-2">
              <div>
                <p className={`font-semibold text-sm ${cfg.color}`}>
                  {cfg.label}
                </p>
                <p className="text-xs text-gray-500">
                  {lead.contact_attempts
                    ? `${lead.contact_attempts} attempts`
                    : "No attempts yet"}
                </p>
              </div>
            </div>
            {(lead.contact_attempts ?? 0) > 0 && (
              <div className="flex items-center gap-1 px-2 py-1 bg-white/60 rounded-full">
                <Phone size={12} className="text-gray-500" />
                <span className="text-xs font-bold text-gray-600">
                  {lead.contact_attempts}
                </span>
              </div>
            )}
          </div>

          {/* VIEW: ACTIONS */}
          {view === "actions" && (
            <>
              <div className="px-5 pt-4 pb-2">
                <div className="flex items-center gap-1.5 mb-2">
                  <FileText size={13} className="text-gray-400" />
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Note (optional — saved with any action)
                  </label>
                </div>
                <textarea
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Add a note about this interaction..."
                  rows={2}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="px-5 py-3">
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <Calendar size={14} /> Schedule
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => openScheduleView("schedule_consultation")}
                    className="flex items-center gap-2 p-3 rounded-xl border-2 border-emerald-200 bg-emerald-50 hover:bg-emerald-100 active:scale-[0.98]"
                  >
                    <div className="w-8 h-8 rounded-lg bg-emerald-100 border border-emerald-200 flex items-center justify-center">
                      <Stethoscope size={16} className="text-emerald-600" />
                    </div>
                    <p className="font-semibold text-sm text-emerald-700">
                      Consultation
                    </p>
                    <ArrowRight
                      size={14}
                      className="text-emerald-400 ml-auto"
                    />
                  </button>
                  <button
                    onClick={() => openScheduleView("schedule_callback")}
                    className="flex items-center gap-2 p-3 rounded-xl border-2 border-violet-200 bg-violet-50 hover:bg-violet-100 active:scale-[0.98]"
                  >
                    <div className="w-8 h-8 rounded-lg bg-violet-100 border border-violet-200 flex items-center justify-center">
                      <CalendarPlus size={16} className="text-violet-600" />
                    </div>
                    <p className="font-semibold text-sm text-violet-700">
                      Callback
                    </p>
                    <ArrowRight size={14} className="text-violet-400 ml-auto" />
                  </button>
                </div>
              </div>
              <div className="px-5 pb-5 pt-1">
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <PhoneCall size={14} /> Record Call Outcome
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  {OUTCOMES.map((o) => (
                    <button
                      key={o.key}
                      onClick={() => {
                        setPendingOutcome(o.key);
                        setView("confirmation");
                      }}
                      className={`p-3 rounded-xl border-2 text-left transition-all hover:scale-[1.02] active:scale-[0.98] ${currentOutcome === o.key ? `${o.bg} ${o.border} ring-2 ring-opacity-50` : "bg-white border-gray-200 hover:border-gray-300 hover:bg-gray-50"}`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center border ${o.bg} ${o.border}`}
                        >
                          {o.icon}
                        </div>
                        <p className={`font-semibold text-sm ${o.color}`}>
                          {o.label}
                        </p>
                        <ArrowRight
                          size={14}
                          className="text-gray-400 ml-auto"
                        />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* VIEW: CONFIRMATION */}
          {view === "confirmation" && pendingOutcome && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => {
                  setView("actions");
                  setPendingOutcome(null);
                }}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back to actions
              </button>
              {(() => {
                const o = OUTCOMES.find((x) => x.key === pendingOutcome)!;
                return (
                  <div
                    className={`rounded-xl border-2 p-4 ${o.bg} ${o.border}`}
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center border ${o.bg} ${o.border}`}
                      >
                        {o.icon}
                      </div>
                      <div>
                        <h4 className={`font-bold text-base ${o.color}`}>
                          Mark as {o.label}
                        </h4>
                        <p className="text-sm text-gray-600">{o.desc}</p>
                      </div>
                    </div>
                    {noteText.trim() && (
                      <div className="mt-3 p-2 bg-white/60 rounded-lg border border-gray-200">
                        <p className="text-xs font-medium text-gray-500 mb-1">
                          📝 Note will be saved:
                        </p>
                        <p className="text-sm text-gray-700">
                          {noteText.trim()}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })()}
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setView("actions");
                    setPendingOutcome(null);
                  }}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl font-semibold disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-white bg-blue-600 hover:bg-blue-700 rounded-xl font-semibold shadow-lg active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Saving...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={18} /> Confirm
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* VIEW: SCHEDULE CONSULTATION */}
          {view === "schedule_consultation" && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => setView("actions")}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back
              </button>
              <div className="text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-emerald-100 flex items-center justify-center mb-2">
                  <Stethoscope size={24} className="text-emerald-600" />
                </div>
                <h4 className="font-bold text-gray-900">
                  Schedule Consultation
                </h4>
                <p className="text-sm text-gray-500">
                  Book consultation for {lead.first_name}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Date
                  </label>
                  <input
                    type="date"
                    value={schedDate}
                    onChange={(e) => {
                      setSchedDate(e.target.value);
                      setSchedError(null);
                    }}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Time
                  </label>
                  <input
                    type="time"
                    value={schedTime}
                    onChange={(e) => {
                      setSchedTime(e.target.value);
                      setSchedError(null);
                    }}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>
              {schedError && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 px-3 py-2 rounded-lg border border-red-200">
                  <AlertCircle size={16} />
                  <span className="text-sm">{schedError}</span>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setView("actions")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl font-semibold disabled:opacity-50"
                >
                  Back
                </button>
                <button
                  onClick={() => handleScheduleSubmit("consultation")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-semibold shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />{" "}
                      Scheduling...
                    </>
                  ) : (
                    <>
                      <Stethoscope size={18} /> Schedule
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* VIEW: SCHEDULE CALLBACK */}
          {view === "schedule_callback" && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => setView("actions")}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back
              </button>
              <div className="text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-violet-100 flex items-center justify-center mb-2">
                  <CalendarPlus size={24} className="text-violet-600" />
                </div>
                <h4 className="font-bold text-gray-900">Schedule Callback</h4>
                <p className="text-sm text-gray-500">
                  When should we call {lead.first_name} back?
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Date
                  </label>
                  <input
                    type="date"
                    value={schedDate}
                    onChange={(e) => {
                      setSchedDate(e.target.value);
                      setSchedError(null);
                    }}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Time
                  </label>
                  <input
                    type="time"
                    value={schedTime}
                    onChange={(e) => {
                      setSchedTime(e.target.value);
                      setSchedError(null);
                    }}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500"
                  />
                </div>
              </div>
              {schedError && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 px-3 py-2 rounded-lg border border-red-200">
                  <AlertCircle size={16} />
                  <span className="text-sm">{schedError}</span>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setView("actions")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl font-semibold disabled:opacity-50"
                >
                  Back
                </button>
                <button
                  onClick={() => handleScheduleSubmit("callback")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 bg-violet-600 hover:bg-violet-700 text-white rounded-xl font-semibold shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />{" "}
                      Scheduling...
                    </>
                  ) : (
                    <>
                      <CalendarPlus size={18} /> Schedule Callback
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="border-t border-gray-200 px-5 py-3 bg-gray-50 flex items-center justify-between">
            <span className="text-xs text-gray-400">
              Submitted {new Date(lead.created_at).toLocaleDateString()}
            </span>
            <button
              onClick={() => {
                onClose();
                onViewDetails(lead.id);
              }}
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              View Full Profile <ExternalLink size={14} />
            </button>
          </div>
          <div className="px-5 py-2 bg-slate-800 text-center">
            <p className="text-xs text-slate-400">
              Press{" "}
              <kbd className="px-1.5 py-0.5 bg-slate-700 rounded text-slate-300 font-mono text-[10px]">
                Esc
              </kbd>{" "}
              to {view !== "actions" ? "go back" : "close"}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* CONSULTATION PANEL COMPONENT                                              */
/* Replicates NeuroReach ConsultationPanel — for scheduled leads             */
/* ═══════════════════════════════════════════════════════════════════════════ */
function ConsultationPanel({
  lead,
  onClose,
  onViewDetails,
  showToast,
  onLeadUpdated,
  onOutcomeRecorded,
}: {
  lead: Lead;
  onClose: () => void;
  onViewDetails: (id: string) => void;
  showToast: (msg: string, type?: "success" | "error") => void;
  onLeadUpdated: (updatedLead: Partial<Lead> & { id: string }) => void;
  onOutcomeRecorded: (leadId: string) => void;
}) {
  type View = "outcomes" | "confirmation" | "reschedule" | "followup";
  const [view, setView] = useState<View>("outcomes");
  const [pendingOutcome, setPendingOutcome] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [pickerDate, setPickerDate] = useState("");
  const [pickerTime, setPickerTime] = useState("");
  const [pickerError, setPickerError] = useState<string | null>(null);

  // Draggable panel state
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setDragOffset({ x: 0, y: 0 });
  }, [lead.id]);

  const handleDragStart = (e: React.MouseEvent) => {
    isDragging.current = true;
    dragStart.current = {
      x: e.clientX - dragOffset.x,
      y: e.clientY - dragOffset.y,
    };
    const onMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      setDragOffset({
        x: ev.clientX - dragStart.current.x,
        y: ev.clientY - dragStart.current.y,
      });
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (view !== "outcomes") {
          setView("outcomes");
          setPendingOutcome(null);
        } else onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [view, onClose]);

  const executeOutcome = async (outcome: string, scheduledAt?: string) => {
    setIsUpdating(true);
    try {
      const apiMap: Record<string, string> = {
        CONSULTATION_COMPLETE: "complete",
        RESCHEDULE_REQUESTED: "reschedule",
        FOLLOWUP_NEEDED: "followup",
        NO_SHOW: "no_show",
        CANCELLED: "cancelled",
      };
      await leadsAPI.updateConsultationOutcome(lead.id, {
        outcome: apiMap[outcome],
        notes: noteText.trim() || undefined,
        scheduled_callback_at: scheduledAt,
      });
      const name = `${lead.first_name} ${lead.last_name || ""}`.trim();
      const msgs: Record<string, string> = {
        CONSULTATION_COMPLETE: `✓ ${name} marked as Completed`,
        RESCHEDULE_REQUESTED: `✓ ${name} rescheduled`,
        FOLLOWUP_NEEDED: `✓ Follow-up scheduled for ${name}`,
        NO_SHOW: `✓ ${name} → Follow-up (No Show)`,
        CANCELLED: `✓ ${name} → Follow-up (Cancelled)`,
      };
      showToast(msgs[outcome] || `✓ ${name} outcome updated`);
      // Remove lead from current queue and refetch — prevents ghost rows.
      // The consultation-outcome endpoint returns { success, lead_id, ... }
      // (not a full Lead), so we must NOT call onLeadUpdated with it.
      onOutcomeRecorded(lead.id);
    } catch {
      showToast("Failed to update outcome", "error");
      setView("confirmation");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleConfirm = () => {
    if (!pendingOutcome || isUpdating) return;
    if (pendingOutcome === "RESCHEDULE_REQUESTED") {
      const t = new Date();
      t.setDate(t.getDate() + 1);
      setPickerDate(t.toISOString().split("T")[0]);
      const n = new Date();
      n.setHours(n.getHours() + 1, 0, 0, 0);
      setPickerTime(n.toTimeString().slice(0, 5));
      setPickerError(null);
      setView("reschedule");
      return;
    }
    if (pendingOutcome === "FOLLOWUP_NEEDED") {
      const t = new Date();
      t.setDate(t.getDate() + 1);
      setPickerDate(t.toISOString().split("T")[0]);
      const n = new Date();
      n.setHours(n.getHours() + 1, 0, 0, 0);
      setPickerTime(n.toTimeString().slice(0, 5));
      setPickerError(null);
      setView("followup");
      return;
    }
    executeOutcome(pendingOutcome);
  };

  const handleDateSubmit = () => {
    if (!pendingOutcome || isUpdating) return;
    if (!pickerDate || !pickerTime) {
      setPickerError("Please select both date and time");
      return;
    }
    const dt = new Date(`${pickerDate}T${pickerTime}`);
    if (dt < new Date()) {
      setPickerError("Cannot schedule in the past");
      return;
    }
    executeOutcome(pendingOutcome, dt.toISOString());
  };

  const OUTCOMES = [
    {
      key: "CONSULTATION_COMPLETE",
      label: "Complete",
      desc: "Successful consultation",
      icon: <CheckCircle2 size={18} className="text-emerald-500" />,
      color: "text-emerald-700",
      bg: "bg-emerald-50",
      border: "border-emerald-200",
    },
    {
      key: "RESCHEDULE_REQUESTED",
      label: "Reschedule",
      desc: "Different time needed",
      icon: <RefreshCw size={18} className="text-amber-500" />,
      color: "text-amber-700",
      bg: "bg-amber-50",
      border: "border-amber-200",
    },
    {
      key: "FOLLOWUP_NEEDED",
      label: "Follow-up",
      desc: "Second consult required",
      icon: <CalendarPlus size={18} className="text-blue-500" />,
      color: "text-blue-700",
      bg: "bg-blue-50",
      border: "border-blue-200",
    },
    {
      key: "NO_SHOW",
      label: "No Show",
      desc: "Did not attend",
      icon: <UserCheck size={18} className="text-red-500" />,
      color: "text-red-700",
      bg: "bg-red-50",
      border: "border-red-200",
    },
    {
      key: "CANCELLED",
      label: "Cancelled",
      desc: "Consultation cancelled",
      icon: <XCircle size={18} className="text-slate-500" />,
      color: "text-slate-700",
      bg: "bg-slate-100",
      border: "border-slate-300",
    },
  ];

  return (
    <>
      <div className="fixed inset-0 bg-black/5 z-40 pointer-events-none" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="pointer-events-auto w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden"
          style={{ transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` }}
        >
          {/* Header — drag handle */}
          <div
            className="relative bg-gradient-to-r from-blue-800 to-indigo-900 text-white px-5 py-4 cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleDragStart}
          >
            <button
              onClick={onClose}
              className="absolute top-3 right-3 p-1.5 hover:bg-white/10 rounded-lg z-10"
            >
              <X size={18} />
            </button>
            <div className="flex items-center gap-3">
              <div
                className={`w-12 h-12 rounded-xl flex items-center justify-center ${lead.priority === "HOT" ? "bg-red-500/20" : lead.priority === "MEDIUM" ? "bg-amber-500/20" : "bg-slate-500/20"}`}
              >
                {lead.priority === "HOT" ? (
                  <Flame size={24} className="text-red-400" />
                ) : lead.priority === "MEDIUM" ? (
                  <Zap size={24} className="text-amber-400" />
                ) : (
                  <User size={24} className="text-slate-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-lg truncate">
                  {lead.first_name} {lead.last_name || ""}
                </h3>
                <p className="text-blue-200 text-sm truncate uppercase">
                  {conditionLabel(lead)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3">
              <span className="text-xs font-mono text-blue-300 bg-blue-900/50 px-2 py-1 rounded">
                {lead.lead_number}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${priorityBadge(lead.priority)}`}
              >
                {lead.priority}
              </span>
              <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500/30 text-blue-100 rounded-full">
                Scheduled
              </span>
            </div>
          </div>

          {/* Scheduled Banner */}
          {lead.scheduled_callback_at && (
            <div className="px-5 py-3 flex items-center gap-3 border-b bg-green-50 border-green-200">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <Calendar size={20} className="text-green-600" />
              </div>
              <div>
                <p className="font-semibold text-sm text-green-700">
                  {formatDate(lead.scheduled_callback_at)}
                </p>
              </div>
            </div>
          )}

          {/* VIEW: OUTCOMES */}
          {view === "outcomes" && (
            <>
              <div className="px-5 pt-4 pb-2">
                <div className="flex items-center gap-1.5 mb-2">
                  <FileText size={13} className="text-gray-400" />
                  <label className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Note (optional — saved with outcome)
                  </label>
                </div>
                <textarea
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Add a note about this consultation..."
                  rows={2}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="px-5 pb-5 pt-2">
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <CheckCircle2 size={14} /> Record Outcome
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  {OUTCOMES.map((o) => (
                    <button
                      key={o.key}
                      onClick={() => {
                        setPendingOutcome(o.key);
                        setView("confirmation");
                      }}
                      className={`p-3 rounded-xl border-2 text-left transition-all hover:scale-[1.02] active:scale-[0.98] bg-white border-gray-200 hover:border-gray-300 hover:bg-gray-50 ${o.key === "CANCELLED" ? "col-span-2" : ""}`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center border ${o.bg} ${o.border}`}
                        >
                          {o.icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`font-semibold text-sm ${o.color}`}>
                            {o.label}
                          </p>
                          <p className="text-[10px] text-gray-500 truncate">
                            {o.desc}
                          </p>
                        </div>
                        <ArrowRight size={14} className="text-gray-400" />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* VIEW: CONFIRMATION */}
          {view === "confirmation" && pendingOutcome && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => {
                  setView("outcomes");
                  setPendingOutcome(null);
                }}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back
              </button>
              {(() => {
                const o = OUTCOMES.find((x) => x.key === pendingOutcome)!;
                return (
                  <div
                    className={`rounded-xl border-2 p-4 ${o.bg} ${o.border}`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center border ${o.bg} ${o.border}`}
                      >
                        {o.icon}
                      </div>
                      <div>
                        <h4 className={`font-bold ${o.color}`}>{o.label}</h4>
                        <p className="text-sm text-gray-600">{o.desc}</p>
                      </div>
                    </div>
                    {noteText.trim() && (
                      <div className="mt-3 p-2 bg-white/60 rounded-lg border border-gray-200">
                        <p className="text-xs font-medium text-gray-500 mb-1">
                          📝 Note:
                        </p>
                        <p className="text-sm text-gray-700">
                          {noteText.trim()}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })()}
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setView("outcomes");
                    setPendingOutcome(null);
                  }}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 rounded-xl font-semibold disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl font-semibold shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Saving...
                    </>
                  ) : pendingOutcome === "RESCHEDULE_REQUESTED" ||
                    pendingOutcome === "FOLLOWUP_NEEDED" ? (
                    <>
                      <Calendar size={18} /> Select Date →
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={18} /> Confirm
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* VIEW: RESCHEDULE */}
          {view === "reschedule" && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => setView("confirmation")}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back
              </button>
              <div className="text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-amber-100 flex items-center justify-center mb-2">
                  <RefreshCw size={24} className="text-amber-600" />
                </div>
                <h4 className="font-bold text-gray-900">Reschedule</h4>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Date
                  </label>
                  <input
                    type="date"
                    value={pickerDate}
                    onChange={(e) => {
                      setPickerDate(e.target.value);
                      setPickerError(null);
                    }}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Time
                  </label>
                  <input
                    type="time"
                    value={pickerTime}
                    onChange={(e) => {
                      setPickerTime(e.target.value);
                      setPickerError(null);
                    }}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg"
                  />
                </div>
              </div>
              {pickerError && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 px-3 py-2 rounded-lg">
                  <AlertCircle size={16} />
                  <span className="text-sm">{pickerError}</span>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setView("confirmation")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 rounded-xl font-semibold disabled:opacity-50"
                >
                  Back
                </button>
                <button
                  onClick={handleDateSubmit}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 bg-amber-600 text-white rounded-xl font-semibold shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Saving...
                    </>
                  ) : (
                    <>
                      <Calendar size={18} /> Reschedule
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* VIEW: FOLLOWUP */}
          {view === "followup" && (
            <div className="px-5 py-5 space-y-4">
              <button
                onClick={() => setView("confirmation")}
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ArrowLeft size={16} /> Back
              </button>
              <div className="text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-blue-100 flex items-center justify-center mb-2">
                  <CalendarPlus size={24} className="text-blue-600" />
                </div>
                <h4 className="font-bold text-gray-900">Schedule Follow-up</h4>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Date
                  </label>
                  <input
                    type="date"
                    value={pickerDate}
                    onChange={(e) => {
                      setPickerDate(e.target.value);
                      setPickerError(null);
                    }}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Time
                  </label>
                  <input
                    type="time"
                    value={pickerTime}
                    onChange={(e) => {
                      setPickerTime(e.target.value);
                      setPickerError(null);
                    }}
                    className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg"
                  />
                </div>
              </div>
              {pickerError && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 px-3 py-2 rounded-lg">
                  <AlertCircle size={16} />
                  <span className="text-sm">{pickerError}</span>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setView("confirmation")}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 text-gray-700 bg-gray-100 rounded-xl font-semibold disabled:opacity-50"
                >
                  Back
                </button>
                <button
                  onClick={handleDateSubmit}
                  disabled={isUpdating}
                  className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-xl font-semibold shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isUpdating ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Saving...
                    </>
                  ) : (
                    <>
                      <CalendarPlus size={18} /> Schedule
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="border-t border-gray-200 px-5 py-3 bg-gray-50 flex items-center justify-between">
            <span className="text-xs text-gray-400">
              {lead.contact_attempts || 0} contact attempts
            </span>
            <button
              onClick={() => {
                onClose();
                onViewDetails(lead.id);
              }}
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              View Full Profile <ExternalLink size={14} />
            </button>
          </div>
          <div className="px-5 py-2 bg-indigo-900 text-center">
            <p className="text-xs text-indigo-300">
              Press{" "}
              <kbd className="px-1.5 py-0.5 bg-indigo-800 rounded text-indigo-200 font-mono text-[10px]">
                Esc
              </kbd>{" "}
              to {view !== "outcomes" ? "go back" : "close"}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
