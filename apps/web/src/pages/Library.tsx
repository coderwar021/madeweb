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
  const { t } = useI18n();
  useEffect(() => {
    api("/api/v1/apps")
      .then((data) => setApps(data.apps))
      .finally(() => setLoaded(true));
  }, []);
  return (
    <Frame>
      <main className="mx-auto max-w-3xl px-5 py-10">
        <h1 className="font-serif text-4xl">{t("libraryTitle")}</h1>
        <div className="mt-8 space-y-3">
          {apps.map((app) => (
            <Link key={app.id} to={`/studio/${app.slug}`} className="block rounded-2xl border border-white/10 px-4 py-4">
              <div className="flex items-center justify-between">
                <span className="font-medium">{app.name}</span>
                <span className="text-xs text-paper/50">{app.published ? t("published") : t("draft")} · v{app.currentVersion || 1}</span>
              </div>
              <p className="mt-1 text-sm text-paper/55">{app.description}</p>
            </Link>
          ))}
          {loaded && apps.length === 0 && <p className="text-paper/50">{t("libraryEmpty")}</p>}
        </div>
      </main>
    </Frame>
  );
}
