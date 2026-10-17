import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Frame } from "../components/Frame";
import { jobText, stepText, useI18n } from "../i18n";

type Step = { key: string; label: string; zh: string; status: string };
type Job = {
  status: string;
  steps: Step[];
  prompt: string;
  message: string;
  error: string | null;
  result: { slug: string; name: string; version: number; scan: { id: string; ok: boolean }[] } | null;
};

export function Build() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const { t } = useI18n();

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const data = await api(`/api/v1/jobs/${jobId}`);
        if (!stop) setJob(data);
        if (!stop && data.status === "running") setTimeout(poll, 700);
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : t("buildMissing"));
      }
    }
    poll();
    return () => {
      stop = true;
    };
  }, [jobId, t]);

  return (
    <Frame>
      <main className="mx-auto max-w-xl px-5 py-16">
        <p className="text-xs uppercase tracking-[0.22em] text-paper/40">{t("buildCompiler")}</p>
        <h1 className="mt-3 font-serif text-4xl">{job?.result?.name || t("buildGenerating")}</h1>
        {job?.prompt && <p className="mt-4 text-sm leading-6 text-paper/60">“{job.prompt}”</p>}
        <ol className="mt-10 space-y-4">
          {(job?.steps || []).map((step) => (
            <motion.li key={step.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-4">
              <span className={`mt-1 h-2.5 w-2.5 rounded-full ${step.status === "done" ? "bg-lime-300" : step.status === "failed" ? "bg-ember" : step.status === "running" ? "bg-paper" : "bg-white/20"}`} />
              <div>
                <p className={step.status === "pending" ? "text-paper/35" : "text-paper"}>{stepText(t, step.key, step.label)}</p>
              </div>
            </motion.li>
          ))}
        </ol>
        {job?.status === "succeeded" && job.result && (
          <div className="mt-10">
            <p className="text-sm text-lime-200">{jobText(t, job.message)}</p>
            {job.result.scan.length > 0 && (
              <p className="mt-2 text-xs text-paper/50">{t("buildScan")}：{job.result.scan.filter((item) => item.ok).map((item) => item.id).join(" · ")}</p>
            )}
            <Link to={`/studio/${job.result.slug}`} className="mt-6 inline-block rounded-full bg-paper px-5 py-2 text-ink">
              {t("buildOpen")}
            </Link>
          </div>
        )}
        {(error || job?.status === "failed") && (
          <p className="mt-8 text-sm text-ember">{error || jobText(t, job?.error || "")}</p>
        )}
      </main>
    </Frame>
  );
}
