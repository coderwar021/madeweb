import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { translateLabel, useI18n, type Locale } from "../i18n";
import { appApi, uploadFile, type AppUser } from "./api";

type Field = { type: string; label: string; required?: boolean; values?: string[]; target?: string; auto?: string; default?: string };
type Entity = { name: string; label: string; titleField: string; fields: Record<string, Field> };
export type UiNode = {
  tag?: string;
  text?: string;
  children?: UiNode[];
  style?: Record<string, string>;
  bind?: string;
  entity?: string;
  field?: string;
  href?: string;
  srcField?: string;
  submit?: boolean;
  placeholder?: string;
  className?: string;
};
type Page = { page: string; route: string; components?: { type: string; source?: string }[]; ui?: UiNode; nav?: { label: string; route: string }[] };
type Schema = {
  name: string;
  entities: Entity[];
  pages: Page[];
  nav?: { label: string; route: string }[];
  theme: { primary: string; background: string; ink: string; logo: string; tagline: string; currency?: string };
  template?: string;
};
type Item = { id: string; data: Record<string, unknown> };
type Meta = { app: { id: string; owner: boolean; status: string; visibility: string }; schema: Schema; version: number };

export function GeneratedUi({
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
  if (!page.ui) return null;
  return <NodeView node={page.ui} ctx={{ meta, page, params, me, setMe, draft, href }} />;
}

function NodeView({
  node,
  ctx,
  record,
}: {
  node: UiNode;
  ctx: {
    meta: Meta;
    page: Page;
    params: Record<string, string>;
    me: AppUser | null;
    setMe: (user: AppUser | null) => void;
    draft: boolean;
    href: (route: string) => string;
  };
  record?: Item;
}) {
  if (node.bind === "list" && node.entity) return <BoundList node={node} ctx={ctx} />;
  if (node.bind === "form" && node.entity) return <BoundForm node={node} ctx={ctx} />;
  if (node.bind === "detail" && node.entity) return <BoundDetail node={node} ctx={ctx} />;
  if (node.bind === "auth") return <BoundAuth ctx={ctx} />;
  if (node.bind === "nav") return <BoundNav node={node} ctx={ctx} />;
  if (node.bind === "search") return <BoundSearch />;
  return <Paint node={node} ctx={ctx} record={record} />;
}

function Paint({ node, ctx, record }: { node: UiNode; ctx: Parameters<typeof NodeView>[0]["ctx"]; record?: Item }) {
  const { locale } = useI18n();
  const tag = node.tag || "div";
  const style = node.style as React.CSSProperties | undefined;
  const kids = (node.children || []).map((child, index) => <NodeView key={index} node={child} ctx={ctx} record={record} />);
  const text = node.field && record ? display(record.data[node.field], locale) : node.field && !record ? "" : node.text || "";
  if (tag === "img") {
    const fileId = record ? fileIdOf(record.data[node.srcField || ""]) : "";
    if (!fileId) return null;
    return <img src={`/api/v1/runtime/${ctx.meta.app.id}/files/${fileId}`} alt="" style={style} className={node.className} />;
  }
  if (tag === "a" && node.href) {
    const route = fillRoute(node.href, record?.id || ctx.params.id || "");
    return (
      <Link to={ctx.href(route)} style={style} className={node.className}>
        {text}
        {kids}
      </Link>
    );
  }
  if (tag === "input" || tag === "textarea" || tag === "button") return null;
  const Tag = (tag as keyof JSX.IntrinsicElements) || "div";
  return (
    <Tag style={style} className={node.className}>
      {text}
      {kids}
    </Tag>
  );
}

function BoundList({ node, ctx }: { node: UiNode; ctx: Parameters<typeof NodeView>[0]["ctx"] }) {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const { t } = useI18n();
  const entity = ctx.meta.schema.entities.find((item) => item.name === node.entity);
  useEffect(() => {
    if (!entity) return;
    const params = new URLSearchParams({ pageSize: "24" });
    const rel = Object.entries(entity.fields).find(([, spec]) => spec.type === "relation");
    if (rel && ctx.params.id) params.set(`f_${rel[0]}`, ctx.params.id);
    appApi(ctx.meta.app.id, `/entities/${entity.name}?${params.toString()}`, { draft: ctx.draft })
      .then((data) => {
        const rows: Item[] = data.items || [];
        const chatty = Boolean(entity.fields.body && Object.values(entity.fields).some((field) => field.type === "user"));
        setItems(chatty ? [...rows].reverse() : rows);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("siteLoadFailed")));
  }, [ctx.meta.app.id, ctx.draft, ctx.params.id, entity, t]);
  if (!entity) return null;
  if (error) return <p style={{ opacity: 0.6 }}>{error}</p>;
  if (items.length === 0) return <p style={{ opacity: 0.6 }}>{t("siteEmpty")}</p>;
  return (
    <div style={node.style as React.CSSProperties} className={node.className}>
      {items.map((item) => (
        <div key={item.id}>{(node.children || []).map((child, index) => <NodeView key={index} node={child} ctx={ctx} record={item} />)}</div>
      ))}
    </div>
  );
}

function BoundDetail({ node, ctx }: { node: UiNode; ctx: Parameters<typeof NodeView>[0]["ctx"] }) {
  const [item, setItem] = useState<Item | null>(null);
  const { t } = useI18n();
  useEffect(() => {
    if (!node.entity || !ctx.params.id) return;
    appApi(ctx.meta.app.id, `/entities/${node.entity}/${ctx.params.id}`, { draft: ctx.draft })
      .then(setItem)
      .catch(() => setItem(null));
  }, [ctx.meta.app.id, ctx.draft, ctx.params.id, node.entity]);
  if (!ctx.params.id) return null;
  if (!item) return <p style={{ opacity: 0.6 }}>{t("siteOpeningItem")}</p>;
  return (
    <div style={node.style as React.CSSProperties} className={node.className}>
      {(node.children || []).map((child, index) => (
        <NodeView key={index} node={child} ctx={ctx} record={item} />
      ))}
    </div>
  );
}

function BoundForm({ node, ctx }: { node: UiNode; ctx: Parameters<typeof NodeView>[0]["ctx"] }) {
  const entity = ctx.meta.schema.entities.find((item) => item.name === node.entity);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { t, locale } = useI18n();
  const login = ctx.href(ctx.meta.schema.pages.find((page) => page.route === "/login")?.route || "/login");
  const declared = useMemo(() => fieldsIn(node), [node]);
  useEffect(() => {
    if (!entity) return;
    const next: Record<string, unknown> = {};
    const rel = Object.entries(entity.fields).find(([, spec]) => spec.type === "relation");
    if (rel && ctx.params.id) next[rel[0]] = ctx.params.id;
    setValues(next);
  }, [entity, ctx.params.id]);
  if (!entity) return null;
  if (!ctx.me) {
    return (
      <Link to={login} style={{ color: "inherit" }}>
        {t("siteLoginToPost")}
      </Link>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!entity) return;
    setBusy(true);
    setError("");
    try {
      const created = await appApi(ctx.meta.app.id, `/entities/${entity.name}`, { method: "POST", body: values, draft: ctx.draft });
      if (entity.fields.body && ctx.params.id) {
        window.location.assign(ctx.href(fillRoute(ctx.page.route, ctx.params.id)));
        return;
      }
      const detail = ctx.meta.schema.pages.find((page) => page.route.includes(":id"));
      window.location.assign(ctx.href(fillRoute(detail?.route || "/", created.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("siteSaveFailed"));
      setBusy(false);
    }
  }

  const inputs = declared.length
    ? declared
    : Object.entries(entity.fields)
        .filter(([, field]) => field.auto !== "current")
        .map(([name]) => name);

  return (
    <form onSubmit={submit} style={node.style as React.CSSProperties} className={node.className}>
      {(node.children || []).map((child, index) => (
        <FormChild key={index} node={child} entity={entity} values={values} setValues={setValues} ctx={ctx} locale={locale} busy={busy} />
      ))}
      {inputs
        .filter((name) => !declared.includes(name) && entity.fields[name]?.auto !== "current")
        .map((name) => (
          <FieldInput key={name} name={name} field={entity.fields[name]} values={values} setValues={setValues} />
        ))}
      {error && <p>{error}</p>}
    </form>
  );
}

function FormChild({
  node,
  entity,
  values,
  setValues,
  ctx,
  locale,
  busy,
}: {
  node: UiNode;
  entity: Entity;
  values: Record<string, unknown>;
  setValues: (update: Record<string, unknown> | ((current: Record<string, unknown>) => Record<string, unknown>)) => void;
  ctx: Parameters<typeof NodeView>[0]["ctx"];
  locale: Locale;
  busy: boolean;
}) {
  const { t } = useI18n();
  const style = node.style as React.CSSProperties | undefined;
  if (node.tag === "button" && node.submit) {
    return (
      <button type="submit" disabled={busy} style={style} className={node.className}>
        {node.text || t("sitePublish")}
      </button>
    );
  }
  if ((node.tag === "input" || node.tag === "textarea") && node.field && entity.fields[node.field]) {
    return <FieldInput name={node.field} field={entity.fields[node.field]} values={values} setValues={setValues} style={style} placeholder={node.placeholder} multiline={node.tag === "textarea"} />;
  }
  if (node.children?.length) {
    return (
      <div style={style} className={node.className}>
        {node.text}
        {node.children.map((child, index) => (
          <FormChild key={index} node={child} entity={entity} values={values} setValues={setValues} ctx={ctx} locale={locale} busy={busy} />
        ))}
      </div>
    );
  }
  const Tag = ((node.tag || "div") as keyof JSX.IntrinsicElements) || "div";
  return (
    <Tag style={style} className={node.className}>
      {node.text ? translateLabel(locale, node.text) : null}
    </Tag>
  );
}

function FieldInput({
  name,
  field,
  values,
  setValues,
  style,
  placeholder,
  multiline,
}: {
  name: string;
  field: Field;
  values: Record<string, unknown>;
  setValues: (update: Record<string, unknown> | ((current: Record<string, unknown>) => Record<string, unknown>)) => void;
  style?: React.CSSProperties;
  placeholder?: string;
  multiline?: boolean;
}) {
  if (field.type === "relation" && values[name]) return null;
  const value = typeof values[name] === "string" || typeof values[name] === "number" ? String(values[name]) : "";
  if (multiline || field.type === "text") {
    return <textarea value={value} placeholder={placeholder || field.label} style={style} className="w-full" onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))} />;
  }
  return <input value={value} placeholder={placeholder || field.label} style={style} className="w-full" onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))} />;
}

function BoundNav({ node, ctx }: { node: UiNode; ctx: Parameters<typeof NodeView>[0]["ctx"] }) {
  const { locale } = useI18n();
  return (
    <nav style={node.style as React.CSSProperties} className={node.className}>
      {(ctx.meta.schema.nav || []).map((item) => (
        <Link key={item.route} to={ctx.href(item.route)} style={{ marginRight: 16, color: "inherit" }}>
          {translateLabel(locale, item.label)}
        </Link>
      ))}
    </nav>
  );
}

function BoundSearch() {
  const [value, setValue] = useState("");
  const { t } = useI18n();
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const next = new URLSearchParams(window.location.search);
        if (value) next.set("q", value);
        else next.delete("q");
        const qs = next.toString();
        window.location.assign(`${window.location.pathname}${qs ? `?${qs}` : ""}`);
      }}
    >
      <input value={value} onChange={(event) => setValue(event.target.value)} placeholder={t("siteSearch")} className="w-full rounded-full border border-black/10 bg-white px-5 py-3" />
    </form>
  );
}

function BoundAuth({ ctx }: { ctx: Parameters<typeof NodeView>[0]["ctx"] }) {
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { t } = useI18n();
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await appApi(ctx.meta.app.id, "/auth/csrf", { draft: ctx.draft });
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, name };
      const result = await appApi(ctx.meta.app.id, path, { method: "POST", body, draft: ctx.draft });
      ctx.setMe(result.user);
      window.location.assign(ctx.href("/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("siteFail"));
    }
  }
  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3 p-8">
      <h1 className="text-3xl">{mode === "login" ? t("siteLogin") : t("siteRegisterTitle")}</h1>
      {mode === "register" && <input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("authName")} className="w-full rounded-2xl border border-black/10 p-3" />}
      <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={t("authEmail")} className="w-full rounded-2xl border border-black/10 p-3" />
      <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t("authPassword")} type="password" className="w-full rounded-2xl border border-black/10 p-3" />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="rounded-full px-5 py-2 text-white" style={{ background: ctx.meta.schema.theme.primary }}>
        {mode === "login" ? t("siteLogin") : t("siteRegisterTitle")}
      </button>
    </form>
  );
}

function fieldsIn(node: UiNode): string[] {
  const names: string[] = [];
  if (node.field) names.push(node.field);
  for (const child of node.children || []) names.push(...fieldsIn(child));
  return names;
}

function fillRoute(route: string, id: string) {
  return route.replace(":id", id || "");
}

function display(value: unknown, locale: Locale) {
  if (typeof value === "string") return translateLabel(locale, value);
  if (typeof value === "number") return String(value);
  if (value && typeof value === "object") {
    if ("name" in value && typeof value.name === "string") return value.name;
    if ("title" in value && typeof value.title === "string") return value.title;
  }
  return "";
}

function fileIdOf(value: unknown) {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  return "";
}

export function hasUi(page: { ui?: UiNode } | null | undefined): page is { ui: UiNode } {
  return Boolean(page && page.ui && typeof page.ui === "object");
}

