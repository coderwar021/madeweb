import { FormEvent, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { LanguageSwitch, statusText, translateLabel, useI18n, type Locale } from "../i18n";
import { appApi, bootApp, uploadFile, type AppUser } from "./api";
import { GeneratedUi, hasUi } from "./GeneratedUi";

type Field = { type: string; label: string; required?: boolean; values?: string[]; target?: string; auto?: string; default?: string };
type Entity = { name: string; label: string; titleField: string; fields: Record<string, Field> };
type Component = { type: string; title?: string; subtitle?: string; entity?: string; placeholder?: string; field?: string; source?: string; mode?: string };
type Page = { page: string; route: string; components: Component[]; ui?: import("./GeneratedUi").UiNode };
type Schema = {
  name: string;
  entities: Entity[];
  pages: Page[];
  nav?: { label: string; route: string }[];
  theme: { primary: string; background: string; ink: string; logo: string; tagline: string; currency?: string };
};
type Item = { id: string; data: Record<string, unknown> };
type Meta = { app: { id: string; owner: boolean; status: string; visibility: string }; schema: Schema; version: number };

const STATUS_KEYS = new Set(["available", "reserved", "sold", "pending", "confirmed", "cancelled"]);

export function Site() {
  const { slug = "", "*": rest } = useParams();
  const [search] = useSearchParams();
  const draft = search.get("draft") === "1";
  const embed = search.get("embed") === "1";
  const [meta, setMeta] = useState<Meta | null>(null);
  const [me, setMe] = useState<AppUser | null>(null);
  const [error, setError] = useState("");
  const { t, locale } = useI18n();

  useEffect(() => {
    let stop = false;
    api(`/api/v1/sites/${slug}${draft ? "?draft=true" : ""}`)
      .then(async (data) => {
        if (stop) return;
        setMeta(data);
        const user = await bootApp(data.app.id, draft).catch(() => null);
        if (!stop) setMe(user);
      })
      .catch((err) => {
        if (!stop) setError(err instanceof Error ? err.message : t("siteMissing"));
      });
    return () => {
      stop = true;
    };
  }, [slug, draft]);

  if (error) return <div className="grid min-h-screen place-items-center text-paper/70">{error}</div>;
  if (!meta) return <div className="grid min-h-screen place-items-center text-paper/50">{t("siteOpening")}</div>;

  const path = `/${rest || ""}`.replace(/\/$/, "") || "/";
  const matched = matchPage(meta.schema.pages, path === "" ? "/" : path);
  const theme = meta.schema.theme;
  const login = meta.schema.pages.find((page) => (page.components || []).some((item) => item.type === "AuthForm") || page.route === "/login")?.route || "/login";

  function href(route: string) {
    const params = new URLSearchParams();
    if (draft) params.set("draft", "1");
    if (embed) params.set("embed", "1");
    const qs = params.toString();
    return `/s/${slug}${route === "/" ? "" : route}${qs ? `?${qs}` : ""}`;
  }

  if (matched && hasUi(matched.page)) {
    return (
      <div style={{ fontFamily: '"Noto Sans SC", "Noto Sans JP", sans-serif' }}>
        {meta.app.status === "disabled" && <p className="bg-black px-4 py-2 text-center text-sm text-white">{t("siteDisabled")}</p>}
        {meta.app.owner && !embed && (
          <div className="flex justify-end gap-3 px-4 py-2 text-xs">
            <LanguageSwitch tone="light" />
            <Link to={`/studio/${slug}`}>{t("siteBackStudio")}</Link>
          </div>
        )}
        <GeneratedUi meta={meta} page={matched.page} params={matched.params} me={me} setMe={setMe} draft={draft} href={href} />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: theme.background, color: theme.ink, fontFamily: '"Noto Sans SC", "Noto Sans JP", sans-serif' }}>
      {meta.app.status === "disabled" && <p className="bg-black px-4 py-2 text-center text-sm text-white">{t("siteDisabled")}</p>}
      {meta.app.owner && !embed && (
        <div className="flex justify-end px-4 py-2 text-xs">
          <Link to={`/studio/${slug}`}>{t("siteBackStudio")}</Link>
        </div>
      )}
      <header className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 py-5">
        <Link to={href("/")} className="shrink-0 font-serif text-2xl" style={{ fontFamily: "Fraunces, serif" }}>
          {translateLabel(locale, theme.logo)}
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <LanguageSwitch tone="light" />
          {(meta.schema.nav || []).map((item) => (
            <Link key={item.route} to={href(item.route)}>
              {translateLabel(locale, item.label)}
            </Link>
          ))}
          {me ? (
            <button
              type="button"
              onClick={async () => {
                try {
                  await appApi(meta.app.id, "/auth/logout", { method: "POST", body: {}, draft });
                  setMe(null);
                  await bootApp(meta.app.id, draft);
                } catch (err) {
                  setError(err instanceof Error ? err.message : t("siteFail"));
                }
              }}
            >
              {t("siteLogout", { name: me.name })}
            </button>
          ) : (
            <Link to={href(login)}>{t("siteLogin")}</Link>
          )}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-5 pb-16">
        {matched ? (
          <PageView meta={meta} page={matched.page} params={matched.params} me={me} setMe={setMe} draft={draft} href={href} />
        ) : (
          <p>{t("siteNoPage")}</p>
        )}
      </main>
    </div>
  );
}

function PageView({
  meta,
  page,
  params,
  me,
  setMe,
  draft,
  href,
}: {
  meta: Meta;
  page: Page;
  params: Record<string, string>;
  me: AppUser | null;
  setMe: (user: AppUser | null) => void;
  draft: boolean;
  href: (route: string) => string;
}) {
  return (
    <div className="space-y-8">
      {page.components.map((component, index) => {
        if (component.type === "Navbar") return null;
        if (component.type === "Hero") return <Hero key={index} component={component} />;
        if (component.type === "Search") return <SearchBox key={index} component={component} />;
        if (component.type === "Filter") return <FilterChips key={index} meta={meta} component={component} draft={draft} />;
        if (component.type === "ProductGrid" || component.type === "CardGrid") {
          return <CardGrid key={index} meta={meta} source={component.source || ""} draft={draft} href={href} />;
        }
        if (component.type === "Form") return <RecordForm key={index} meta={meta} source={component.source || ""} me={me} draft={draft} href={href} />;
        if (component.type === "Table" || component.type === "Comment") return <RecordTable key={index} meta={meta} source={component.source || ""} draft={draft} />;
        if (component.type === "Detail") return <Detail key={index} meta={meta} source={component.source || ""} id={params.id || ""} me={me} draft={draft} href={href} />;
        if (component.type === "AuthForm") return <AuthPanel key={index} meta={meta} setMe={setMe} draft={draft} href={href} />;
        return null;
      })}
    </div>
  );
}

function Hero({ component }: { component: Component }) {
  const { locale } = useI18n();
  return (
    <section>
      <h1 className="font-serif text-5xl leading-tight" style={{ fontFamily: "Fraunces, serif" }}>
        {translateLabel(locale, component.title || "")}
      </h1>
      {component.subtitle && <p className="mt-3 max-w-xl text-lg opacity-70">{translateLabel(locale, component.subtitle)}</p>}
    </section>
  );
}

function SearchBox({ component }: { component: Component }) {
  const [search, setSearch] = useSearchParams();
  const [value, setValue] = useState(search.get("q") || "");
  const { t, locale } = useI18n();
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const next = new URLSearchParams(search);
        if (value) next.set("q", value);
        else next.delete("q");
        next.delete("page");
        setSearch(next);
      }}
    >
      <input value={value} onChange={(event) => setValue(event.target.value)} placeholder={translateLabel(locale, component.placeholder || t("siteSearch"))} className="w-full rounded-full border border-black/10 bg-white px-5 py-3 outline-none" />
    </form>
  );
}

function FilterChips({ meta, component, draft }: { meta: Meta; component: Component; draft: boolean }) {
  const [search, setSearch] = useSearchParams();
  const [options, setOptions] = useState<Item[]>([]);
  const { t, locale } = useI18n();
  const entity = meta.schema.entities.find((item) => item.name === component.entity);
  useEffect(() => {
    if (!component.entity) return;
    appApi(meta.app.id, `/entities/${component.entity}`, { draft }).then((data) => setOptions(data.items)).catch(() => setOptions([]));
  }, [meta.app.id, component.entity, draft]);
  if (!entity || !component.field) return null;
  const current = search.get(component.field) || "";
  return (
    <div className="flex flex-wrap gap-2">
      <Chip active={!current} onClick={() => setFilter(search, setSearch, component.field || "", "")}>
        {t("siteAll")}
      </Chip>
      {options.map((item) => (
        <Chip key={item.id} active={current === item.id} onClick={() => setFilter(search, setSearch, component.field || "", item.id)}>
          {textOf(item.data[entity.titleField], locale)}
        </Chip>
      ))}
    </div>
  );
}

function CardGrid({ meta, source, draft, href }: { meta: Meta; source: string; draft: boolean; href: (route: string) => string }) {
  const [search, setSearch] = useSearchParams();
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { t, locale } = useI18n();
  const entity = meta.schema.entities.find((item) => item.name === source);
  const page = Number(search.get("page") || "1");
  useEffect(() => {
    if (!entity) return;
    setLoaded(false);
    const params = new URLSearchParams();
    const q = search.get("q");
    if (q) params.set("q", q);
    params.set("page", String(page));
    for (const name of Object.keys(entity.fields)) {
      const value = search.get(name);
      if (value) params.set(`f_${name}`, value);
    }
    appApi(meta.app.id, `/entities/${source}?${params.toString()}`, { draft })
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("siteLoadFailed")))
      .finally(() => setLoaded(true));
  }, [meta.app.id, source, draft, search, entity, page]);
  if (!entity) return null;
  if (!loaded) return <p className="opacity-60">{t("siteLoading")}</p>;
  if (error) return <p className="text-sm opacity-60">{error === "没有查看权限" ? t("siteNoPermission") : error}</p>;
  if (items.length === 0) return <p className="opacity-60">{source === "Favorite" ? t("siteNoFavorites") : t("siteEmpty")}</p>;
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => {
          const title = cardTitle(entity, item.data, locale) || t("siteUntitled");
          const image = cardImage(entity, item.data);
          const price = cardPrice(entity, item.data);
          const direct = detailRoute(meta.schema, source);
          const relTarget = entity.fields[entity.titleField]?.target;
          const relRoute = relTarget ? detailRoute(meta.schema, relTarget) : undefined;
          const linked = direct ? direct.replace(":id", item.id) : relRoute ? relRoute.replace(":id", relatedId(entity, item)) : "";
          const target = linked ? href(linked) : "";
          const body = (
            <article className="overflow-hidden rounded-3xl bg-white shadow-sm">
              <div className="flex h-40 items-center justify-center text-3xl" style={{ background: image ? undefined : meta.schema.theme.primary, color: "white" }}>
                {image ? <img src={fileUrl(meta.app.id, image)} alt="" className="h-full w-full object-cover" /> : title.slice(0, 1)}
              </div>
              <div className="p-4">
                <h2 className="text-lg">{title}</h2>
                {price && <p className="mt-1 font-serif text-xl">{money(price, meta.schema.theme.currency)}</p>}
              </div>
            </article>
          );
          return target ? (
            <Link key={item.id} to={target}>
              {body}
            </Link>
          ) : (
            <div key={item.id}>{body}</div>
          );
        })}
      </div>
      {total > 12 && (
        <div className="mt-4 flex gap-3 text-sm">
          <button disabled={page <= 1} onClick={() => setFilter(search, setSearch, "page", String(page - 1))}>
            {t("sitePrev")}
          </button>
          <button disabled={page * 12 >= total} onClick={() => setFilter(search, setSearch, "page", String(page + 1))}>
            {t("siteNext")}
          </button>
        </div>
      )}
    </div>
  );
}

function Detail({ meta, source, id, me, draft, href }: { meta: Meta; source: string; id: string; me: AppUser | null; draft: boolean; href: (route: string) => string }) {
  const [item, setItem] = useState<Item | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [note, setNote] = useState("");
  const [body, setBody] = useState("");
  const { t, locale } = useI18n();
  const entity = meta.schema.entities.find((entry) => entry.name === source);
  const favorite = meta.schema.entities.find((entry) => entry.name === "Favorite");
  const message = meta.schema.entities.find((entry) => entry.name === "Message");
  const order = meta.schema.entities.find((entry) => entry.name === "Order");
  useEffect(() => {
    setLoaded(false);
    setItem(null);
    appApi(meta.app.id, `/entities/${source}/${id}`, { draft })
      .then(setItem)
      .catch(() => setItem(null))
      .finally(() => setLoaded(true));
  }, [meta.app.id, source, id, draft]);
  if (!entity) return null;
  if (!loaded) return <p className="opacity-60">{t("siteOpeningItem")}</p>;
  if (!item) return <p>{t("siteNotFound")}</p>;
  const title = cardTitle(entity, item.data, locale) || t("siteUntitled");
  const image = cardImage(entity, item.data);
  const seller = item.data.sellerId as { id?: string; name?: string } | undefined;
  const login = href(meta.schema.pages.find((page) => page.components.some((c) => c.type === "AuthForm"))?.route || "/login");

  async function toggleFavorite() {
    if (!me || !favorite) return;
    const field = Object.entries(favorite.fields).find(([, spec]) => spec.target === source)?.[0] || "productId";
    try {
      const existing = await appApi(meta.app.id, `/entities/Favorite?f_${field}=${id}`, { draft });
      if (existing.items[0]) await appApi(meta.app.id, `/entities/Favorite/${existing.items[0].id}`, { method: "DELETE", draft });
      else await appApi(meta.app.id, "/entities/Favorite", { method: "POST", body: { [field]: id }, draft });
      setNote(existing.items[0] ? t("siteUnfavorited") : t("siteFavorited"));
    } catch (err) {
      setNote(err instanceof Error ? err.message : t("siteFail"));
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!message || !seller?.id) return;
    if (!body.trim()) {
      setNote(t("siteNeedText"));
      return;
    }
    const rel = Object.entries(message.fields).find(([, spec]) => spec.target === source)?.[0];
    try {
      await appApi(meta.app.id, "/entities/Message", {
        method: "POST",
        draft,
        body: { body, recipientId: seller.id, ...(rel ? { [rel]: id } : {}) },
      });
      setBody("");
      setNote(t("siteSent"));
    } catch (err) {
      setNote(err instanceof Error ? err.message : t("siteFail"));
    }
  }

  async function placeOrder() {
    if (!order) return;
    const rel = Object.entries(order.fields).find(([, spec]) => spec.target === source)?.[0] || "productId";
    try {
      await appApi(meta.app.id, "/entities/Order", { method: "POST", body: { [rel]: id }, draft });
      setNote(t("siteReserved"));
    } catch (err) {
      setNote(err instanceof Error ? err.message : t("siteFail"));
    }
  }

  return (
    <article className="grid gap-8 md:grid-cols-2">
      <div className="flex min-h-72 items-center justify-center rounded-3xl" style={{ background: meta.schema.theme.primary }}>
        {image ? <img src={fileUrl(meta.app.id, image)} alt="" className="max-h-[28rem] w-full rounded-3xl object-cover" /> : <span className="font-serif text-6xl text-white">{title.slice(0, 1)}</span>}
      </div>
      <div>
        <h1 className="font-serif text-4xl" style={{ fontFamily: "Fraunces, serif" }}>{title}</h1>
        {item.data.price != null && <p className="mt-3 font-serif text-3xl">{money(item.data.price, meta.schema.theme.currency)}</p>}
        {typeof item.data.status === "string" && <p className="mt-2 text-sm opacity-60">{statusText(locale, item.data.status)}</p>}
        {typeof item.data.location === "string" && <p className="mt-1 text-sm opacity-60">{item.data.location}</p>}
        {typeof item.data.description === "string" && <p className="mt-4 leading-7">{item.data.description}</p>}
        {seller?.name && <p className="mt-4 text-sm">{t("siteSeller", { name: seller.name })}</p>}
        <div className="mt-6 flex flex-wrap gap-2">
          {favorite && (me ? <Action onClick={toggleFavorite}>{t("siteFavorite")}</Action> : <Link to={login}>{t("siteLoginToFavorite")}</Link>)}
          {order && me && <Action onClick={placeOrder}>{t("siteReserve")}</Action>}
        </div>
        {message && me && (
          <form onSubmit={sendMessage} className="mt-6 space-y-2">
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder={t("siteContact")} className="h-24 w-full rounded-2xl border border-black/10 p-3" />
            <Action type="submit">{t("siteSend")}</Action>
          </form>
        )}
        {note && <p className="mt-3 text-sm">{note}</p>}
      </div>
    </article>
  );
}

function RecordForm({ meta, source, me, draft, href }: { meta: Meta; source: string; me: AppUser | null; draft: boolean; href: (route: string) => string }) {
  const entity = meta.schema.entities.find((item) => item.name === source);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [options, setOptions] = useState<Record<string, Item[]>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { t, locale } = useI18n();
  const login = href(meta.schema.pages.find((page) => page.components.some((c) => c.type === "AuthForm"))?.route || "/login");
  useEffect(() => {
    if (!entity) return;
    for (const [name, field] of Object.entries(entity.fields)) {
      if (field.type === "relation" && field.target) {
        appApi(meta.app.id, `/entities/${field.target}`, { draft }).then((data) => setOptions((current) => ({ ...current, [name]: data.items }))).catch(() => undefined);
      }
    }
  }, [entity, meta.app.id, draft]);
  if (!entity) return null;
  if (!me) return <Link to={login}>{t("siteLoginToPost")}</Link>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await appApi(meta.app.id, `/entities/${source}`, { method: "POST", body: values, draft });
      const route = detailRoute(meta.schema, source);
      window.location.assign(route ? href(route.replace(":id", created.id)) : href("/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("siteSaveFailed"));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-4">
      <h1 className="font-serif text-4xl">{t("sitePublishEntity", { name: translateLabel(locale, entity.label) })}</h1>
      {Object.entries(entity.fields).map(([name, field]) => {
        if (field.auto === "current") return null;
        return (
          <label key={name} className="block text-sm">
            {translateLabel(locale, field.label)}
            {field.type === "text" && <textarea className="mt-1 h-28 w-full rounded-2xl border border-black/10 p-3" onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))} />}
            {field.type === "enum" && (
              <select
                className="mt-1 w-full rounded-2xl border border-black/10 bg-white p-3"
                value={typeof values[name] === "string" ? (values[name] as string) : field.default || ""}
                onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
              >
                {!field.default && <option value="">{t("siteChoose")}</option>}
                {(field.values || []).map((value) => (
                  <option key={value} value={value}>
                    {statusText(locale, value)}
                  </option>
                ))}
              </select>
            )}
            {field.type === "relation" && (
              <select className="mt-1 w-full rounded-2xl border border-black/10 bg-white p-3" onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}>
                <option value="">{t("siteChoose")}</option>
                {(options[name] || []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {textOf(item.data.title || item.data.name, locale)}
                  </option>
                ))}
              </select>
            )}
            {(field.type === "file" || field.type === "file[]") && (
              <input
                className="mt-1 block"
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                multiple={field.type === "file[]"}
                onChange={async (event) => {
                  const input = event.target;
                  const files = [...(input.files || [])];
                  setError("");
                  try {
                    const ids: string[] = [];
                    for (const file of files) ids.push((await uploadFile(meta.app.id, file, draft)).id);
                    setValues((current) => ({ ...current, [name]: field.type === "file[]" ? ids : ids[0] }));
                  } catch (err) {
                    input.value = "";
                    setError(err instanceof Error ? err.message : t("siteSaveFailed"));
                  }
                }}
              />
            )}
            {["string", "decimal", "integer"].includes(field.type) && (
              <input
                className="mt-1 w-full rounded-2xl border border-black/10 p-3"
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    [name]: field.type === "integer" ? (event.target.value === "" ? "" : Number(event.target.value)) : event.target.value,
                  }))
                }
              />
            )}
          </label>
        );
      })}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button disabled={busy} className="rounded-full px-5 py-2 text-white" style={{ background: meta.schema.theme.primary }}>
        {busy ? t("sitePublishing") : t("sitePublish")}
      </button>
    </form>
  );
}

function RecordTable({ meta, source, draft }: { meta: Meta; source: string; draft: boolean }) {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const { t, locale } = useI18n();
  const entity = meta.schema.entities.find((item) => item.name === source);
  useEffect(() => {
    appApi(meta.app.id, `/entities/${source}`, { draft })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : t("siteLoadFailed")));
  }, [meta.app.id, source, draft]);
  if (!entity) return null;
  if (error) return <p className="text-sm opacity-60">{error}</p>;
  if (items.length === 0) return <p className="opacity-60">{t("siteNoContent")}</p>;
  const fields = Object.keys(entity.fields).slice(0, 4);
  return (
    <div className="overflow-hidden rounded-3xl bg-white">
      {items.map((item) => (
        <div key={item.id} className="grid gap-2 border-b border-black/5 px-4 py-3 text-sm sm:grid-cols-4">
          {fields.map((name) => (
            <span key={name}>{textOf(item.data[name], locale)}</span>
          ))}
        </div>
      ))}
    </div>
  );
}

function AuthPanel({ meta, setMe, draft, href }: { meta: Meta; setMe: (user: AppUser | null) => void; draft: boolean; href: (route: string) => string }) {
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { t } = useI18n();

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await appApi(meta.app.id, "/auth/csrf", { draft });
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, name };
      const result = await appApi(meta.app.id, path, { method: "POST", body, draft });
      setMe(result.user);
      window.location.assign(href("/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("siteFail"));
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3">
      <h1 className="font-serif text-4xl">{mode === "login" ? t("siteLogin") : t("siteRegisterTitle")}</h1>
      {mode === "register" && <input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("authName")} className="w-full rounded-2xl border border-black/10 p-3" />}
      <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={t("authEmail")} className="w-full rounded-2xl border border-black/10 p-3" />
      <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t("authPassword")} type="password" className="w-full rounded-2xl border border-black/10 p-3" />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="rounded-full px-5 py-2 text-white" style={{ background: meta.schema.theme.primary }}>
        {mode === "login" ? t("siteLogin") : t("siteRegisterTitle")}
      </button>
      <button type="button" className="block text-sm opacity-60" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? t("siteNewAccount") : t("authHasAccount")}
      </button>
    </form>
  );
}

function Action({ children, onClick, type = "button" }: { children: React.ReactNode; onClick?: () => void; type?: "button" | "submit" }) {
  return (
    <button type={type} onClick={onClick} className="rounded-full bg-black px-4 py-2 text-sm text-white">
      {children}
    </button>
  );
}

function Chip({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded-full px-3 py-1 text-sm" style={{ background: active ? "#1c1917" : "white", color: active ? "white" : "#1c1917" }}>
      {children}
    </button>
  );
}

function matchPage(pages: Page[], path: string) {
  const normalized = path === "" ? "/" : path;
  for (const page of [...pages].sort((a, b) => b.route.length - a.route.length)) {
    const params = matchRoute(page.route, normalized);
    if (params) return { page, params };
  }
  return null;
}

function matchRoute(route: string, path: string) {
  const left = route.split("/").filter(Boolean);
  const right = path.split("/").filter(Boolean);
  if (route === "/" && path === "/") return {};
  if (left.length !== right.length) return null;
  const params: Record<string, string> = {};
  for (let index = 0; index < left.length; index += 1) {
    if (left[index].startsWith(":")) params[left[index].slice(1)] = decodeURIComponent(right[index]);
    else if (left[index] !== right[index]) return null;
  }
  return params;
}

function detailRoute(schema: Schema, source: string) {
  return schema.pages.find((page) => page.components.some((item) => item.type === "Detail" && item.source === source))?.route;
}

function cardTitle(entity: Entity, data: Record<string, unknown>, locale: Locale) {
  return textOf(data[entity.titleField], locale);
}

function cardImage(entity: Entity, data: Record<string, unknown>) {
  const title = data[entity.titleField];
  if (title && typeof title === "object" && "image" in title && typeof title.image === "string") return title.image;
  for (const [name, field] of Object.entries(entity.fields)) {
    if (field.type === "file[]" && Array.isArray(data[name]) && typeof data[name][0] === "string") return data[name][0];
    if (field.type === "file" && typeof data[name] === "string") return data[name];
  }
  return "";
}

function cardPrice(entity: Entity, data: Record<string, unknown>) {
  const title = data[entity.titleField];
  if (title && typeof title === "object" && "price" in title && (typeof title.price === "string" || typeof title.price === "number")) return title.price;
  if (typeof data.price === "string" || typeof data.price === "number") return data.price;
  return undefined;
}

function relatedId(entity: Entity, item: Item) {
  const value = item.data[entity.titleField];
  if (value && typeof value === "object" && "id" in value && typeof value.id === "string") return value.id;
  return item.id;
}

function textOf(value: unknown, locale: Locale) {
  if (typeof value === "string") return STATUS_KEYS.has(value) ? statusText(locale, value) : translateLabel(locale, value);
  if (typeof value === "number") return String(value);
  if (value && typeof value === "object") {
    if ("name" in value && typeof value.name === "string") return value.name;
    if ("title" in value && typeof value.title === "string") return translateLabel(locale, value.title);
  }
  return "";
}

function money(value: unknown, currency?: string) {
  const number = Number(value);
  if (Number.isNaN(number)) return String(value ?? "");
  if (currency === "JPY") return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(number);
  if (currency === "CNY") return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(number);
  return String(value);
}

function fileUrl(appId: string, fileId: string) {
  return `/api/v1/runtime/${appId}/files/${fileId}`;
}

function setFilter(search: URLSearchParams, setSearch: (next: URLSearchParams) => void, key: string, value: string) {
  const next = new URLSearchParams(search);
  if (value) next.set(key, value);
  else next.delete(key);
  if (key !== "page") next.delete("page");
  setSearch(next);
}
