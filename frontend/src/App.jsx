import { useEffect } from "react";
import { useStore } from "./store";
import Sidebar from "./components/Sidebar";
import HQ from "./components/HQ";
import Brain from "./components/Brain";
import Scouting from "./components/Scouting";
import Desk from "./components/Desk";
import TrainRael from "./components/TrainRael";
import Pipeline from "./components/Pipeline";
import Outreach from "./components/Outreach";
import Relationships from "./components/Relationships";
import Reports from "./components/Reports";
import LeadPanel from "./components/LeadPanel";
import EnrichPrompt from "./components/EnrichPrompt";
import Ticker from "./components/Ticker";
import RaelNow from "./components/RaelNow";
import Auth from "./components/Auth";

export default function App() {
  const view = useStore((s) => s.view);
  const init = useStore((s) => s.init);
  const authStatus = useStore((s) => s.authStatus);

  useEffect(() => {
    init();
  }, [init]);

  if (authStatus === "loading") {
    return <div className="flex items-center justify-center min-h-screen text-muted">Loading...</div>;
  }

  if (authStatus === "unauthenticated") {
    return <Auth />;
  }

  if (authStatus === "onboard_pending") {
    return (
      <div className="w-full h-screen bg-base overflow-y-auto">
        <div className="max-w-5xl mx-auto pt-10 pb-16">
          <TrainRael />
        </div>
      </div>
    );
  }

  return (
    <div className="os-shell">
      <Sidebar />
      <div className="os-main-wrap">
        <RaelNow />
        <main className="os-main">
          {view === "hq" && <HQ />}
          {view === "brain" && <Brain />}
          {view === "scouting" && <Scouting />}
          {view === "relationships" && <Relationships />}
          {view === "pipeline" && <Pipeline />}
          {view === "outreach" && <Outreach />}
          {view === "desk" && <Desk />}
          {view === "train" && <TrainRael />}
          {view === "results" && <Reports />}
        </main>
        <Ticker />
      </div>

      {/* overlays */}
      <LeadPanel />
      <EnrichPrompt />
    </div>
  );
}
