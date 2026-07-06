import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

export default function Reports() {
  const { metrics, leads, fit } = useStore(useShallow((s) => ({ metrics: s.metrics, leads: s.leads, fit: s.fit })));

  const threshold =
    parseInt((fit || []).find((r) => r.parameter_name === "qualify_threshold")?.parameter_value) || 65;

  // Score distribution across leads — a quick read on Fit Model behavior.
  const buckets = [
    { name: "0–49", v: 0, color: "#94A3B8" },
    { name: "50–64", v: 0, color: "#F59E0B" },
    { name: "65–79", v: 0, color: "#6366F1" },
    { name: "80–100", v: 0, color: "#10B981" },
  ];
  leads.forEach((l) => {
    const s = l.fit_score;
    if (s == null) return;
    if (s < 50) buckets[0].v++;
    else if (s < 65) buckets[1].v++;
    else if (s < 80) buckets[2].v++;
    else buckets[3].v++;
  });

  const funnel = [
    { n: metrics.in_pipeline ?? 0, t: "companies in pipeline" },
    { n: metrics.contacted ?? 0, t: "prospects contacted" },
    { n: metrics.replies ?? 0, t: "conversations started" },
    { n: metrics.meetings ?? 0, t: "meetings booked" },
  ];

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Results</div>
      <h1 className="screen-title">What my work has produced.</h1>
      <p className="screen-sub">The funnel end to end, and how my scoring is behaving against your bar.</p>

      <div className="rp-cards">
        {funnel.map((c) => (
          <div key={c.t} className="rp-card">
            <div className="rp-num">{c.n}</div>
            <div className="rp-label">{c.t}</div>
          </div>
        ))}
        <div className="rp-card accent">
          <div className="rp-num">${(metrics.pipeline_value ?? 0).toLocaleString()}</div>
          <div className="rp-label">pipeline created</div>
        </div>
      </div>

      <div className="rp-chart">
        <div className="rp-chart-title">Fit score distribution</div>
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={buckets}>
            <XAxis dataKey="name" stroke="#7A8699" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke="#7A8699" fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} width={28} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              contentStyle={{ background: "#141A23", border: "1px solid rgba(255,255,255,0.11)", borderRadius: 10, color: "#E8EDF4", fontSize: 13 }}
            />
            <Bar dataKey="v" radius={[7, 7, 0, 0]}>
              {buckets.map((b, i) => <Cell key={i} fill={b.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="rp-chart-note">
          Your qualification bar is <b>{threshold}</b> — companies scoring at or above it are the ones I act on.
        </p>
      </div>
    </div>
  );
}
