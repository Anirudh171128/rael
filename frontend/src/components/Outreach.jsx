import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { timeAgo } from "../util";

const TABS = [
  { key: "drafts", label: "Drafts", hint: "waiting for your sign-off" },
  { key: "sent", label: "Sent", hint: "already out the door" },
  { key: "inbox", label: "Inbox", hint: "replies from prospects" },
];

function channelIcon(ch) {
  if (ch === "email") return "✉";
  if (ch === "linkedin") return "in";
  if (ch === "whatsapp") return "💬";
  return "📨";
}

function classTag(outcome) {
  if (!outcome) return null;
  const map = {
    warm: ["warm", "WARM"], faq: ["faq", "FAQ"], objection: ["obj", "OBJECTION"],
    "out of office": ["ooo", "OOO"], unsubscribe: ["unsub", "UNSUB"],
  };
  return map[outcome?.toLowerCase?.()] || null;
}

function subjectFor(i) {
  return i.subject || (i.company_name ? `Quick note for ${i.company_name}` : "(no subject)");
}

export default function Outreach() {
  const { outreach, refreshOutreach, approve, openLead, saveDraft } = useStore(
    useShallow((s) => ({
      outreach: s.outreach, refreshOutreach: s.refreshOutreach,
      approve: s.approve, openLead: s.openLead, saveDraft: s.saveDraft,
    }))
  );
  const [tab, setTab] = useState("drafts");
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    refreshOutreach();
  }, [refreshOutreach]);

  const items = outreach[tab] || [];
  const openItem = useMemo(
    () => [...outreach.drafts, ...outreach.sent, ...outreach.inbox].find((i) => i.id === openId) || null,
    [outreach, openId]
  );

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Outreach</div>
      <h1 className="screen-title">Messages, drafts, and replies.</h1>
      <p className="screen-sub">
        {outreach.drafts.length > 0
          ? `${outreach.drafts.length} draft${outreach.drafts.length > 1 ? "s" : ""} waiting for your sign-off — click one to read, edit, and send.`
          : "All drafts reviewed — Rael is handling the rest."}
      </p>

      {/* Tab bar */}
      <div className="or-tabs">
        {TABS.map((t) => {
          const count = (outreach[t.key] || []).length;
          return (
            <button
              key={t.key}
              className={`or-tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
              {count > 0 && <span className="or-tab-count">{count}</span>}
            </button>
          );
        })}
      </div>

      {items.length === 0 ? (
        <div className="hq-help-empty" style={{ marginTop: 24 }}>
          {tab === "drafts" && "No pending drafts — you're all clear."}
          {tab === "sent" && "Nothing sent yet — once Rael reaches out, messages appear here."}
          {tab === "inbox" && "No replies yet — they'll show up here when prospects respond."}
        </div>
      ) : (
        <div className="or-list">
          {items.map((i) => {
            const cls = classTag(i.outcome);
            return (
              <button className="or-row" key={i.id} onClick={() => setOpenId(i.id)}>
                <span className="or-channel">{channelIcon(i.channel)}</span>
                <span className="or-row-who">
                  {i.contact_name || i.company_name || "—"}
                  {i.company_name && i.contact_name && <span className="or-row-co"> · {i.company_name}</span>}
                </span>
                <span className="or-row-snippet">
                  {tab !== "inbox" && <b>{subjectFor(i)}</b>}
                  {tab !== "inbox" && " — "}
                  {i.content}
                </span>
                {cls && <span className={`or-cls ${cls[0]}`}>{cls[1]}</span>}
                {tab === "drafts" && <span className="or-row-badge">NEEDS YOU</span>}
                <span className="or-row-time">{timeAgo(i.sent_at || i.created_at)}</span>
              </button>
            );
          })}
        </div>
      )}

      {openItem && (
        <MessageModal
          item={openItem}
          onClose={() => setOpenId(null)}
          approve={approve}
          saveDraft={saveDraft}
          openLead={openLead}
        />
      )}
    </div>
  );
}

// ── Centered reader/editor ────────────────────────────────────────────────
function MessageModal({ item, onClose, approve, saveDraft, openLead }) {
  const isDraft = item.outcome === "pending_approval";
  const isInbound = item.direction === "inbound";
  const [subject, setSubject] = useState(subjectFor(item));
  const [content, setContent] = useState(item.content || "");
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  const dirty = subject !== subjectFor(item) || content !== (item.content || "");

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    setSaving(true);
    try {
      await saveDraft(item.id, { subject, content });
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1800);
    } finally {
      setSaving(false);
    }
  };

  const sendNow = async () => {
    setSending(true);
    try {
      if (dirty) await saveDraft(item.id, { subject, content });
      await approve(item.lead_id, "send");
      onClose();
    } finally {
      setSending(false);
    }
  };

  const skip = async () => {
    await approve(item.lead_id, "skip");
    onClose();
  };

  const eyebrow = isDraft
    ? `Draft · ${item.channel || "email"} · awaiting your approval`
    : isInbound
      ? `Reply · ${item.channel || "email"}${item.outcome ? ` · classified ${item.outcome}` : ""}`
      : `Sent · ${item.channel || "email"}${item.sent_at ? ` · ${timeAgo(item.sent_at)}` : ""}`;

  // Portal to <body>: ancestors animate with transforms (.rise), which would
  // otherwise re-anchor position:fixed and pin the modal to the screen's top.
  return createPortal(
    <div className="or-overlay" onMouseDown={onClose}>
      <div className="or-modal rise" onMouseDown={(e) => e.stopPropagation()}>
        <div className="or-modal-head">
          <div>
            <div className="or-modal-eyebrow">{eyebrow}</div>
            <div className="or-modal-who">
              {isInbound ? "From" : "To"}: <b>{item.contact_name || "the decision maker"}</b>
              {item.company_name && <span className="or-modal-co"> · {item.company_name}</span>}
            </div>
          </div>
          <button className="or-modal-x" onClick={onClose}>×</button>
        </div>

        {!isInbound && (
          <div className="or-field">
            <label className="or-field-k">Subject</label>
            {isDraft ? (
              <input className="or-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
            ) : (
              <div className="or-subject readonly">{subjectFor(item)}</div>
            )}
          </div>
        )}

        <div className="or-field grow">
          <label className="or-field-k">{isInbound ? "Their message" : "Body"}</label>
          {isDraft ? (
            <textarea
              className="or-body-edit"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={10}
              spellCheck
            />
          ) : (
            <div className="or-body-read">{item.content}</div>
          )}
        </div>

        <div className="or-modal-foot">
          {item.lead_id && (
            <button className="cta ghost" onClick={() => { onClose(); openLead(item.lead_id); }}>
              Open lead →
            </button>
          )}
          <div className="spacer" style={{ flex: 1 }} />
          {isDraft ? (
            <>
              <button className="cta" onClick={skip}>Skip</button>
              <button className="cta" onClick={save} disabled={saving || !dirty}>
                {saving ? "Saving…" : savedFlash ? "Saved ✓" : "Save changes"}
              </button>
              <button className="cta primary" onClick={sendNow} disabled={sending || !content.trim()}>
                {sending ? "Sending…" : dirty ? "Save & send" : "Send it"}
              </button>
            </>
          ) : (
            <button className="cta" onClick={onClose}>Close</button>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
