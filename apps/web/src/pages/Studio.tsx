import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { LanguageSwitch, useI18n } from "../i18n";

type SiteMeta = {
  app: { id: string; name: string; owner: boolean; dirty: boolean; visibility: string };
  version: number;
};

export function Studio() {
  const { slug = "" } = useParams();
  const [meta, setMeta] = useState<SiteMeta | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [promptTouched, setPromptTouched] = useState(false);
  const [notice, setNotice] = useState("");
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    api(`/api/v1/sites/${slug}?draft=true`)
      .then(setMeta)
      .catch((err) => setError(err instanceof Error ? err.message : t("studioCantOpen")));
  }, [slug, t]);

  useEffect(() => {
    if (!promptTouched) setPrompt(t("editExample"));
  }, [promptTouched, t]);

  async function remix() {
    if (!meta) return;
    setNotice("");
    try {
      const result = await api(`/api/v1/apps/${meta.app.id}/remix`, { method: "POST", body: {} });
      navigate(`/studio/${result.app.slug}`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t("studioCantOpen"));
    }
  }

  async function edit() {
    if (!meta) return;
    setNotice("");
    try {
      const job = await api(`/api/v1/apps/${meta.app.id}/edits`, { method: "POST", body: { prompt } });
      navigate(`/build/${job.jobId}`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t("studioCantOpen"));
    }
  }

  async function share() {
    const url = `${window.location.origin}/s/${slug}`;
    let copied = false;
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
    } catch {
      copied = false;
    }
    const privacy = meta?.app.visibility === "private" ? t("studioPrivate") : "";
    setNotice(copied ? t("studioCopied", { extra: privacy, url }) : t("studioShareLink", { url }));
  }

  if (error) {
    return <p className="p-10 text-ember">{error}</p>;
  }

  return (
    <div className="flex h-screen flex-col bg-ink">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <Link to="/library" className="text-sm text-paper/60">
            {t("studioBack")}
          </Link>
          <p className="max-w-full truncate font-serif text-lg">{meta?.app.name || slug}</p>
          <span className="text-xs text-paper/40">v{meta?.version || ""}</span>
          {meta?.app.dirty && <span className="text-xs text-lime-200">{t("studioDirty")}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <LanguageSwitch />
          <button onClick={() => setEditing(true)} className="rounded-full px-3 py-1 ring-1 ring-white/15">
            {t("studioEdit")}
          </button>
          <button onClick={share} className="rounded-full px-3 py-1 ring-1 ring-white/15">
            {t("studioShare")}
          </button>
          <button onClick={remix} className="rounded-full px-3 py-1 ring-1 ring-white/15">
            {t("studioRemix")}
          </button>
          <Link to={`/publish/${slug}`} className="rounded-full bg-paper px-3 py-1 text-ink">
            {t("studioPublish")}
          </Link>
        </div>
      </header>
      {notice && <p className="bg-white/5 px-4 py-2 text-sm text-paper/70">{notice}</p>}
      <iframe title="preview" src={`/s/${slug}?draft=1&embed=1`} className="min-h-0 w-full flex-1 border-0 bg-[#f4f0e6]" />
      {editing && (
        <div className="border-t border-white/10 p-4">
          <p className="text-sm text-paper/60">{t("studioHint")}</p>
          <div className="mt-3 flex gap-2">
            <input
              value={prompt}
              onChange={(event) => {
                setPromptTouched(true);
                setPrompt(event.target.value);
              }}
              className="flex-1 rounded-full bg-white/5 px-4 py-2 outline-none ring-1 ring-white/10"
            />
            <button onClick={edit} className="rounded-full bg-ember px-4 py-2 text-white">
              {t("studioApply")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
