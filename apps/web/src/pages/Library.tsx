import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Frame } from "../components/Frame";
import { useI18n } from "../i18n";

type AppCard = {
  id: string;
  slug: string;
  name: string;
  description: string;
  visibility: string;
  currentVersion: number | null;
  published: boolean;
  dirty: boolean;
};

export function Library() {
  const [apps, setApps] = useState<AppCard[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const { t } = useI18n();

  function load() {
    api("/api/v1/apps")
      .then((data) => setApps(data.apps))
      .catch((err) => setError(err instanceof Error ? err.message : t("libraryEmpty")))
      .finally(() => setLoaded(true));
  }

  useEffect(load, [t]);

  async function unpublish(event: React.MouseEvent, app: AppCard) {
    event.preventDefault();
    event.stopPropagation();
    setError("");
    try {
      await api(`/api/v1/apps/${app.id}/unpublish`, { method: "POST", body: {} });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }

  async function remove(event: React.MouseEvent, app: AppCard) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm(t("libraryDeleteConfirm", { name: app.name }))) return;
    setError("");
    try {
      await api(`/api/v1/apps/${app.id}`, { method: "DELETE" });
      setApps((current) => current.filter((item) => item.id !== app.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }

  return (
    <Frame>
      <main className="mx-auto max-w-3xl px-5 py-10">
        <h1 className="font-serif text-4xl">{t("libraryTitle")}</h1>
        {error && <p className="mt-4 text-ember">{error}</p>}
        <div className="mt-8 space-y-3">
          {apps.map((app) => (
            <div key={app.id} className="rounded-2xl border border-white/10 px-4 py-4">
              <Link to={`/studio/${app.slug}`} className="block">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{app.name}</span>
                  <span className="text-xs text-paper/50">{app.published ? t("published") : t("draft")} · v{app.currentVersion || 1}</span>
                </div>
                <p className="mt-1 text-sm text-paper/55">{app.description}</p>
              </Link>
              <div className="mt-3 flex flex-wrap gap-3 text-sm">
                {app.published && (
                  <button type="button" onClick={(event) => unpublish(event, app)} className="text-paper/70">
                    {t("libraryUnpublish")}
                  </button>
                )}
                <button type="button" onClick={(event) => remove(event, app)} className="text-ember">
                  {t("libraryDelete")}
                </button>
              </div>
            </div>
          ))}
          {loaded && apps.length === 0 && <p className="text-paper/50">{t("libraryEmpty")}</p>}
        </div>
      </main>
    </Frame>
  );
}
