import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, refreshAnonCsrf, takePrompt } from "../api";
import { useAuth } from "../auth";
import { Frame } from "../components/Frame";
import { useI18n } from "../i18n";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { setUser } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await refreshAnonCsrf();
      const path = mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, name };
      const result = await api(path, { method: "POST", body });
      setUser(result.user);
      const pending = takePrompt();
      if (pending) {
        const job = await api("/api/v1/apps", { method: "POST", body: { prompt: pending } });
        navigate(`/build/${job.jobId}`);
        return;
      }
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("authFailed"));
      setBusy(false);
    }
  }

  return (
    <Frame>
      <form onSubmit={submit} className="mx-auto mt-16 max-w-md px-5">
        <h1 className="font-serif text-4xl">{mode === "login" ? t("authLogin") : t("authRegister")}</h1>
        <p className="mt-2 text-sm text-paper/60">{mode === "login" ? t("authLoginLead") : t("authRegisterLead")}</p>
        <div className="mt-8 space-y-3">
          {mode === "register" && (
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("authName")} className="w-full rounded-2xl bg-white/5 px-4 py-3 outline-none ring-1 ring-white/10" />
          )}
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={t("authEmail")} type="email" className="w-full rounded-2xl bg-white/5 px-4 py-3 outline-none ring-1 ring-white/10" />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t("authPassword")} type="password" className="w-full rounded-2xl bg-white/5 px-4 py-3 outline-none ring-1 ring-white/10" />
        </div>
        {error && <p className="mt-3 text-sm text-ember">{error}</p>}
        <button disabled={busy} className="mt-6 w-full rounded-full bg-paper py-3 text-ink disabled:opacity-60">
          {busy ? t("authWait") : mode === "login" ? t("authLogin") : t("authContinue")}
        </button>
        <p className="mt-4 text-sm text-paper/60">
          {mode === "login" ? <Link to="/register">{t("authNoAccount")}</Link> : <Link to="/login">{t("authHasAccount")}</Link>}
        </p>
      </form>
    </Frame>
  );
}
