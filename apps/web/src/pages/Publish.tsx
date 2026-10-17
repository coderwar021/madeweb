import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { LanguageSwitch, useI18n } from "../i18n";

type Agent = { id: string; name: string; status: string };
type AppInfo = { id: string; slug: string; name: string; visibility: string; published: boolean };

export function Publish() {
  const { slug = "" } = useParams();
  const [app, setApp] = useState<AppInfo | null>(null);
  const [target, setTarget] = useState<"platform" | "server" | "">("");
  const [visibility, setVisibility] = useState<"public" | "unlisted" | "private">("public");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [enroll, setEnroll] = useState<{ enrollCommand: string; runCommand: string } | null>(null);
  const [live, setLive] = useState("");
  const [error, setError] = useState("");
  const [deployment, setDeployment] = useState("");
  const { t } = useI18n();

  useEffect(() => {
    api(`/api/v1/sites/${slug}?draft=true`)
      .then((data) => setApp(data.app))
      .catch((err) => setError(err instanceof Error ? err.message : t("publishFailed")));
    api("/api/v1/agents")
      .then((data) => {
        setAgents(data.agents);
        if (data.agents[0]) setAgentId(data.agents[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("publishFailed")));
  }, [slug, t]);

  async function refreshAgents() {
    const data = await api("/api/v1/agents");
    setAgents(data.agents);
  }

  async function createAgent() {
    setError("");
    try {
      const created = await api("/api/v1/agents", { method: "POST", body: { name: t("agentName") } });
      setEnroll({ enrollCommand: created.enrollCommand, runCommand: created.runCommand });
      setAgentId(created.agent.id);
      await refreshAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishFailed"));
    }
  }

  async function publish() {
    if (!app || !target) return;
    setError("");
    try {
      const result = await api(`/api/v1/apps/${app.id}/publish`, {
        method: "POST",
        body: { target, visibility, agentId: target === "server" ? agentId : undefined },
      });
      if (target === "platform") {
        setLive(`${window.location.origin}/s/${slug}`);
        setDeployment("succeeded");
      } else {
        setDeployment(result.deployment.status);
        setLive(`${window.location.origin}/s/${slug}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishFailed"));
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={`/studio/${slug}`} className="text-sm text-paper/50">
          {t("publishBack")}
        </Link>
        <LanguageSwitch />
      </div>
      <h1 className="mt-4 font-serif text-5xl">{t("publishTitle")}</h1>
      {app?.name && <p className="mt-3 text-paper/60">{t("publishLead", { name: app.name })}</p>}
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <button onClick={() => setTarget("platform")} className={`rounded-3xl border p-5 text-left ${target === "platform" ? "border-ember" : "border-white/10"}`}>
          <p className="text-2xl">☁ {t("publishPlatform")}</p>
          <p className="mt-2 text-sm text-paper/60">{t("publishPlatformBody")}</p>
        </button>
        <button onClick={() => setTarget("server")} className={`rounded-3xl border p-5 text-left ${target === "server" ? "border-ember" : "border-white/10"}`}>
          <p className="text-2xl">🖥 {t("publishServer")}</p>
          <p className="mt-2 text-sm text-paper/60">{t("publishServerBody")}</p>
        </button>
      </div>
      {target === "platform" && (
        <fieldset className="mt-6 space-y-2 text-sm">
          <legend className="mb-2 text-paper/50">{t("publishWho")}</legend>
          {(
            [
              ["public", t("visPublic")],
              ["unlisted", t("visUnlisted")],
              ["private", t("visPrivate")],
            ] as const
          ).map(([id, label]) => (
            <label key={id} className="flex gap-2">
              <input type="radio" checked={visibility === id} onChange={() => setVisibility(id as typeof visibility)} />
              {label}
            </label>
          ))}
        </fieldset>
      )}
      {target === "server" && (
        <section className="mt-6 rounded-3xl border border-white/10 p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">{t("publishConnect")}</h2>
            <button onClick={createAgent} className="text-sm text-ember">
              {t("publishCreateAgent")}
            </button>
          </div>
          <button onClick={refreshAgents} className="mt-3 text-xs text-paper/40">
            {t("publishRefresh")}
          </button>
          <div className="mt-3 space-y-2">
            {agents.map((agent) => (
              <label key={agent.id} className="flex items-center justify-between rounded-2xl bg-white/5 px-3 py-2 text-sm">
                <span>
                  <input type="radio" className="mr-2" checked={agentId === agent.id} onChange={() => setAgentId(agent.id)} />
                  {agent.name}
                </span>
                <span className="text-paper/50">{agent.status === "pending" ? t("agentPending") : agent.status === "online" ? t("agentOnline") : t("agentOffline")}</span>
              </label>
            ))}
          </div>
          {enroll && (
            <div className="mt-4 space-y-3 text-xs text-paper/70">
              <p>{t("publishTokenOnce")}</p>
              <pre className="overflow-x-auto rounded-2xl bg-black/40 p-3">{enroll.enrollCommand}</pre>
              <pre className="overflow-x-auto rounded-2xl bg-black/40 p-3">{enroll.runCommand}</pre>
            </div>
          )}
          <p className="mt-4 text-xs text-paper/40">{t("publishDomain")}</p>
        </section>
      )}
      {target && (
        <button onClick={publish} className="mt-6 rounded-full bg-paper px-5 py-2 text-ink">
          {target === "platform" ? t("publishToPlatform") : t("publishToServer")}
        </button>
      )}
      {error && <p className="mt-4 text-sm text-ember">{error}</p>}
      {live && (
        <section className="mt-8 rounded-3xl bg-white/5 p-5">
          <p className="font-serif text-3xl">{t("publishLive")}</p>
          <a className="mt-3 block text-ember" href={live}>
            {live}
          </a>
          {deployment === "queued" && <p className="mt-3 text-sm text-paper/60">{t("publishQueued")}</p>}
          <div className="mt-4 flex gap-4 text-sm">
            <Link to={`/studio/${slug}`}>{t("publishKeepEditing")}</Link>
            <Link to="/explore">{t("publishExplore")}</Link>
          </div>
        </section>
      )}
    </main>
  );
}
