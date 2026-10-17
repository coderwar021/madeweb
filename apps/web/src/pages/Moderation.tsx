import { useEffect, useState } from "react";
import { api } from "../api";
import { Frame } from "../components/Frame";
import { useI18n } from "../i18n";

export function Moderation() {
  const [queue, setQueue] = useState<{ reports: { id: string; appId: string; reason: string; details: string }[]; disabled: { id: string; name: string; appeal: string | null }[] }>({ reports: [], disabled: [] });
  const [error, setError] = useState("");
  const { t } = useI18n();

  function load() {
    api("/api/v1/moderation/queue").then(setQueue).catch((err) => setError(err instanceof Error ? err.message : t("noPermission")));
  }
  useEffect(load, [t]);

  async function disable(appId: string) {
    try {
      await api(`/api/v1/moderation/apps/${appId}/disable`, { method: "POST", body: { note: "review" } });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }
  async function restore(appId: string) {
    try {
      await api(`/api/v1/moderation/apps/${appId}/restore`, { method: "POST", body: {} });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }

  return (
    <Frame>
      <main className="mx-auto max-w-3xl px-5 py-10">
        <h1 className="font-serif text-4xl">{t("moderationTitle")}</h1>
        {error && <p className="mt-4 text-ember">{error}</p>}
        <section className="mt-8 space-y-3">
          {queue.reports.map((report) => (
            <div key={report.id} className="rounded-2xl border border-white/10 p-4 text-sm">
              <p>{report.reason}</p>
              <p className="text-paper/60">{report.details || t("noDetails")}</p>
              <button className="mt-2 text-ember" onClick={() => disable(report.appId)}>
                {t("takedown")}
              </button>
            </div>
          ))}
          {queue.reports.length === 0 && <p className="text-paper/50">{t("noReports")}</p>}
        </section>
        <section className="mt-8 space-y-3">
          {queue.disabled.map((app) => (
            <div key={app.id} className="rounded-2xl border border-white/10 p-4">
              <p>{app.name}</p>
              {app.appeal && <p className="text-sm text-paper/60">{t("appeal", { text: app.appeal })}</p>}
              <button className="mt-2 text-sm" onClick={() => restore(app.id)}>
                {t("restore")}
              </button>
            </div>
          ))}
        </section>
      </main>
    </Frame>
  );
}
