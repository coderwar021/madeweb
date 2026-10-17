import { FormEvent, useEffect, useState } from "react";
import { api, PlatformUser } from "../api";
import { useAuth } from "../auth";
import { Frame } from "../components/Frame";
import { useI18n } from "../i18n";

type Account = PlatformUser;

export function Users() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Account[]>([]);
  const [selected, setSelected] = useState<Account | null>(null);
  const [name, setName] = useState("");
  const [group, setGroup] = useState("default");
  const [quota, setQuota] = useState("20");
  const [status, setStatus] = useState<"active" | "disabled">("active");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function load(q = query) {
    const path = q.trim() ? `/api/v1/users?q=${encodeURIComponent(q.trim())}` : "/api/v1/users";
    api(path)
      .then((data) => {
        const users = data.users as Account[];
        setRows(users);
        setSelected((current) => (current && users.some((row) => row.id === current.id) ? current : null));
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("noPermission")));
  }

  useEffect(() => {
    load(query);
    // Reload when the language changes, keeping the current search text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  function choose(row: Account) {
    setSelected(row);
    setName(row.name);
    setGroup(row.group);
    setQuota(String(row.quota));
    setStatus(row.status);
    setNotice("");
    setError("");
  }

  function apply(next: Account) {
    setRows((current) => current.map((row) => (row.id === next.id ? next : row)));
    setSelected(next);
    setName(next.name);
    setGroup(next.group);
    setQuota(String(next.quota));
    setStatus(next.status);
    setNotice(t("usersSaved"));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setError("");
    try {
      const data = await api(`/api/v1/users/${selected.id}`, {
        method: "PUT",
        body: { name, group, quota: Number(quota), status },
      });
      apply(data.user);
    } catch (err) {
      setNotice("");
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }

  async function manage(action: "enable" | "disable" | "delete" | "promote" | "demote") {
    if (!selected) return;
    setError("");
    try {
      const data = await api(`/api/v1/users/${selected.id}/manage`, { method: "POST", body: { action } });
      if (action === "delete") {
        setRows((current) => current.filter((row) => row.id !== selected.id));
        setSelected(null);
        setNotice(t("usersSaved"));
        return;
      }
      apply(data.user);
    } catch (err) {
      setNotice("");
      setError(err instanceof Error ? err.message : t("noPermission"));
    }
  }

  function roleLabel(role: Account["role"]) {
    if (role === "root") return t("usersRoleRoot");
    if (role === "admin") return t("usersRoleAdmin");
    return t("usersRoleUser");
  }

  const locked = !selected || selected.id === user?.id || selected.role === "root";

  return (
    <Frame>
      <main className="mx-auto max-w-5xl px-5 py-10">
        <h1 className="font-serif text-4xl">{t("usersTitle")}</h1>
        <p className="mt-3 max-w-2xl text-paper/70">{t("usersLead")}</p>
        <form
          className="mt-6 flex gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            load();
          }}
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("usersSearch")}
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
          />
          <button type="submit" className="rounded-full border border-white/15 px-5 py-2">
            {t("usersFind")}
          </button>
        </form>
        {error && <p className="mt-4 text-ember">{error}</p>}
        {notice && <p className="mt-4 text-paper/80">{notice}</p>}
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-paper/50">
              <tr>
                <th className="py-2 pr-3 font-normal">{t("usersName")}</th>
                <th className="py-2 pr-3 font-normal">{t("usersEmail")}</th>
                <th className="py-2 pr-3 font-normal">{t("usersRole")}</th>
                <th className="py-2 pr-3 font-normal">{t("usersGroup")}</th>
                <th className="py-2 pr-3 font-normal">{t("usersQuota")}</th>
                <th className="py-2 pr-3 font-normal">{t("usersUsed")}</th>
                <th className="py-2 font-normal">{t("usersStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-white/10">
                  <td className="py-3 pr-3">
                    <button type="button" className="underline decoration-white/30 underline-offset-4" onClick={() => choose(row)}>
                      {row.name}
                    </button>
                  </td>
                  <td className="py-3 pr-3">{row.email}</td>
                  <td className="py-3 pr-3">{roleLabel(row.role)}</td>
                  <td className="py-3 pr-3">{row.group}</td>
                  <td className="py-3 pr-3">{row.quota}</td>
                  <td className="py-3 pr-3">{row.usedQuota}</td>
                  <td className="py-3">{row.status === "disabled" ? t("usersStatusDisabled") : t("usersStatusActive")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <p className="mt-4 text-paper/60">{t("usersEmpty")}</p>}
        </div>
        {selected && (
          <form onSubmit={save} className="mt-8 grid gap-4 rounded-3xl border border-white/10 p-5 sm:grid-cols-2">
            <label className="block text-sm">
              {t("usersName")}
              <input value={name} onChange={(event) => setName(event.target.value)} disabled={locked} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3" />
            </label>
            <label className="block text-sm">
              {t("usersGroup")}
              <input value={group} onChange={(event) => setGroup(event.target.value)} disabled={locked} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3" />
            </label>
            <label className="block text-sm">
              {t("usersQuota")}
              <input value={quota} onChange={(event) => setQuota(event.target.value)} disabled={locked} inputMode="numeric" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3" />
            </label>
            <label className="block text-sm">
              {t("usersStatus")}
              <select value={status} onChange={(event) => setStatus(event.target.value as "active" | "disabled")} disabled={locked} className="mt-2 w-full rounded-2xl border border-white/10 bg-ink px-4 py-3">
                <option value="active">{t("usersStatusActive")}</option>
                <option value="disabled">{t("usersStatusDisabled")}</option>
              </select>
            </label>
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <button type="submit" disabled={locked} className="rounded-full bg-paper px-5 py-2 text-ink disabled:opacity-40">
                {t("usersSave")}
              </button>
              <button type="button" disabled={locked} onClick={() => manage(status === "disabled" ? "enable" : "disable")} className="rounded-full border border-white/15 px-5 py-2 disabled:opacity-40">
                {status === "disabled" ? t("usersEnable") : t("usersDisable")}
              </button>
              {user?.role === "root" && selected.role === "user" && (
                <button type="button" onClick={() => manage("promote")} className="rounded-full border border-white/15 px-5 py-2">
                  {t("usersPromote")}
                </button>
              )}
              {user?.role === "root" && selected.role === "admin" && (
                <button type="button" onClick={() => manage("demote")} className="rounded-full border border-white/15 px-5 py-2">
                  {t("usersDemote")}
                </button>
              )}
              <button type="button" disabled={locked} onClick={() => manage("delete")} className="rounded-full border border-white/15 px-5 py-2 text-ember disabled:opacity-40">
                {t("usersDelete")}
              </button>
            </div>
          </form>
        )}
      </main>
    </Frame>
  );
}
