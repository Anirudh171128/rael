import { useState } from "react";
import { useStore } from "../store";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

export default function Auth() {
  const login = useStore((s) => s.login);
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSend = async (e) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError("");
    try {
      await login(email);
      setStep(2);
    } catch (err) {
      setError("Failed to send code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    if (!otp) return;
    setLoading(true);
    setError("");
    try {
      await login(email, otp);
    } catch (err) {
      setError("Invalid code. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-base">
      <div className="w-full max-w-md p-8 rounded-2xl bg-surface border border-white/10 shadow-3xl text-center">
        <div className="mb-6 flex justify-center">
          <img src={RAEL_IMG} alt="Rael" className="w-16 h-16 rounded-full" />
        </div>
        <h1 className="text-2xl font-serif font-bold text-ink mb-2">Welcome to Rael</h1>
        <p className="text-muted text-sm mb-8">
          {step === 1 ? "Enter your email to sign in or create an account." : `We sent a code to ${email}`}
        </p>

        {error && <div className="text-danger bg-danger/10 border border-danger/20 p-3 rounded-lg mb-6 text-sm">{error}</div>}

        {step === 1 ? (
          <form onSubmit={handleSend} className="space-y-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              className="w-full bg-card border border-white/10 rounded-lg px-4 py-3 text-ink focus:border-accent/50 outline-none"
              autoFocus
              required
            />
            <button
              type="submit"
              disabled={loading || !email}
              className="w-full bg-accent hover:bg-accent/90 text-white font-medium py-3 rounded-lg transition disabled:opacity-50"
            >
              {loading ? "Sending..." : "Continue with Email"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="space-y-4">
            <input
              type="text"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="6-digit code"
              className="w-full bg-card border border-white/10 rounded-lg px-4 py-3 text-ink focus:border-accent/50 outline-none text-center tracking-widest text-lg"
              autoFocus
              required
            />
            <button
              type="submit"
              disabled={loading || !otp}
              className="w-full bg-accent hover:bg-accent/90 text-white font-medium py-3 rounded-lg transition disabled:opacity-50"
            >
              {loading ? "Verifying..." : "Verify Code"}
            </button>
            <button
              type="button"
              onClick={() => setStep(1)}
              className="text-muted text-sm mt-4 hover:text-ink transition"
            >
              Use a different email
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
