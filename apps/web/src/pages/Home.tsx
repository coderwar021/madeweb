import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, rememberPrompt } from "../api";
import { useAuth } from "../auth";
import { Frame } from "../components/Frame";
import { useI18n } from "../i18n";

export function Home() {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  async function create() {
    const text = prompt.trim();
    if (!text) {
      setError(t("homeNeedPrompt"));
      return;
    }
    if (!user) {
      rememberPrompt(text);
      navigate("/register");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const job = await api("/api/v1/apps", { method: "POST", body: { prompt: text } });
      navigate(`/build/${job.jobId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("homeFailed"));
      setBusy(false);
    }
  }

  return (
    <Frame>
      <main className="mx-auto flex max-w-3xl flex-col px-5 pb-20 pt-10">
        <p className="text-xs uppercase tracking-[0.28em] text-paper/50">{t("homeKicker")}</p>
        <h1 className="mt-4 font-serif text-5xl leading-tight text-paper sm:text-6xl">{t("homeTitle")}</h1>
        <p className="mt-4 max-w-xl text-paper/70">{t("homeLead")}</p>
        <div className="prompt mt-8 rounded-3xl p-3">
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={t("homePlaceholder")}
            className="h-36 w-full resize-none bg-transparent px-3 py-2 text-lg text-ink outline-none placeholder:text-ink/40"
          />
          <div className="flex flex-col gap-3 px-2 pb-1 sm:flex-row sm:items-center sm:justify-between">
            <button type="button" className="min-w-0 text-left text-sm text-ink/60 hover:text-ink" onClick={() => setPrompt(t("example"))}>
              {t("homeTry")}: {t("example")}
            </button>
            <button
              type="button"
              onClick={create}
              disabled={busy}
              className="shrink-0 rounded-full bg-ember px-5 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {busy ? t("homeCreating") : t("homeCreate")}
            </button>
          </div>
        </div>
        {error && <p className="mt-3 text-sm text-ember">{error}</p>}
        <div className="mt-10 grid gap-3 sm:grid-cols-3">
          {[
            [t("cardPlatformTitle"), t("cardPlatform")],
            [t("cardServerTitle"), t("cardServer")],
            [t("cardSelfTitle"), t("cardSelf")],
          ].map(([title, copy]) => (
            <div key={title} className="rounded-2xl border border-white/10 px-4 py-4">
              <p className="font-medium">{title}</p>
              <p className="mt-2 text-sm leading-6 text-paper/60">{copy}</p>
            </div>
          ))}
        </div>
        <p className="mt-10 text-xs tracking-wide text-paper/40">{t("homeFoot")}</p>
      </main>
    </Frame>
  );
}
