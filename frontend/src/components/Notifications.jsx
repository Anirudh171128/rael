import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

// Mirrors the WhatsApp notifications Rael sends the rep. Interactive buttons map
// to the same approval/lead actions the real WhatsApp buttons trigger.
export default function Notifications() {
  const { notifications, dismissNotification, approve, openLead } = useStore(useShallow((s) => ({
    notifications: s.notifications,
    dismissNotification: s.dismissNotification,
    approve: s.approve,
    openLead: s.openLead,
  })));

  function handle(n, label) {
    const l = label.toLowerCase();
    if (n.lead_id && (l.includes("send"))) approve(n.lead_id, "send");
    else if (n.lead_id && (l.includes("skip") || l.includes("ignore"))) approve(n.lead_id, "skip");
    else if (n.lead_id && (l.includes("thread") || l.includes("view") || l.includes("brief") || l.includes("edit") || l.includes("call")))
      openLead(n.lead_id);
    dismissNotification(n._id);
  }

  return (
    <div className="fixed bottom-16 right-4 z-[60] w-80 space-y-2">
      <AnimatePresence>
        {notifications.map((n) => (
          <motion.div
            key={n._id}
            initial={{ opacity: 0, x: 60, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60 }}
            className="rounded-xl bg-[#0b141a] border border-success/20 shadow-xl overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 py-2 bg-[#1f2c33]">
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-indigo-800 grid place-items-center text-[11px] font-bold text-white">R</div>
              <span className="text-xs font-semibold text-success">Rael</span>
              <span className="text-[10px] text-muted ml-auto">WhatsApp</span>
              <button onClick={() => dismissNotification(n._id)} className="text-muted hover:text-ink text-sm">×</button>
            </div>
            <div className="px-3 py-2.5">
              <div className="text-sm font-semibold">{n.emoji} {n.title}</div>
              <div className="text-sm text-ink/90 mt-1 whitespace-pre-wrap">{n.body}</div>
              {n.buttons?.length > 0 && (
                <div className="flex gap-1.5 mt-2.5 flex-wrap">
                  {n.buttons.map((b) => (
                    <button
                      key={b}
                      onClick={() => handle(n, b)}
                      className="text-xs px-2.5 py-1 rounded-md bg-[#1f2c33] border border-success/20 text-success hover:bg-success/10 transition"
                    >
                      {b}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
