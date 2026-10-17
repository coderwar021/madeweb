import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Frame } from "../components/Frame";
import { useI18n, type MessageKey } from "../i18n";

type Card = {
  id: string;
  slug: string;
  name: string;
  description: string;
  likeCount: number;
  remixCount: number;
  viewCount: number;
  liked: boolean;
};

const SORTS: [string, MessageKey][] = [
  ["trending", "sortTrending"],
  ["new", "sortNew"],
  ["popular", "sortPopular"],
  ["remixed", "sortRemixed"],
  ["used", "sortUsed"],
];

export function Explore() {
  const [sort, setSort] = useState("trending");
  const [apps, setApps] = useState<Card[]>([]);
  const [loaded, setLoaded] = useState(false);
  const { user } = useAuth();
  const { t } = useI18n();

  useEffect(() => {
    setLoaded(false);
    api(`/api/v1/explore?sort=${sort}`)
      .then((data) => setApps(data.apps))
      .finally(() => setLoaded(true));
  }, [sort]);

  async function like(app: Card) {
    if (!user) return;
    const result = await api(`/api/v1/apps/${app.id}/like`, { method: "POST", body: {} });
    setApps((current) => current.map((item) => (item.id === app.id ? { ...item, liked: result.liked, likeCount: result.likeCount } : item)));
  }

  return (
    <Frame>
      <main className="mx-auto max-w-6xl px-5 py-8">
        <h1 className="font-serif text-5xl">{t("exploreTitle")}</h1>
        <div className="mt-6 flex flex-wrap gap-2">
          {SORTS.map(([id, label]) => (
            <button key={id} onClick={() => setSort(id)} className={`rounded-full px-3 py-1 text-sm ${sort === id ? "bg-paper text-ink" : "bg-white/5 text-paper/70"}`}>
              {t(label)}
            </button>
          ))}
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {apps.map((app) => (
            <article key={app.id} className="rounded-3xl border border-white/10 p-5">
              <Link to={`/s/${app.slug}`} className="font-serif text-2xl">
                {app.name}
              </Link>
              <p className="mt-2 min-h-12 text-sm text-paper/60">{app.description}</p>
              <div className="mt-4 flex items-center justify-between text-sm text-paper/50">
                <span>{t("exploreStats", { views: app.viewCount, remixes: app.remixCount })}</span>
                <button onClick={() => like(app)} className={app.liked ? "text-ember" : ""}>
                  {t("likeCount", { n: app.likeCount })}
                </button>
              </div>
            </article>
          ))}
          {loaded && apps.length === 0 && <p className="text-paper/50">{t("exploreEmpty")}</p>}
        </div>
      </main>
    </Frame>
  );
}
