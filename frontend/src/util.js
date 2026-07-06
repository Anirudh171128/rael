// Small shared helpers.

export const clampScore = (s) => (s == null ? null : Math.max(0, Math.min(100, Math.round(s))));

// Confidence/score → semantic color (Brain bars, score badges).
export function scoreColor(s) {
  const v = clampScore(s) ?? 0;
  if (v >= 90) return "var(--sage)";
  if (v >= 70) return "var(--honey)";
  return "var(--clay)";
}

export function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const d = (Date.now() - t) / 1000;
  if (d < 90) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}
