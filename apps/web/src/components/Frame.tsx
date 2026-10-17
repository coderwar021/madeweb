import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { LanguageSwitch, useI18n } from "../i18n";

export function Frame({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { t } = useI18n();
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 py-5">
        <Link to="/" className="font-serif text-xl tracking-tight">
          AI Web Platform
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-paper/80">
          <LanguageSwitch />
          <Link to="/explore">{t("navExplore")}</Link>
          {user && <Link to="/library">{t("navLibrary")}</Link>}
          {user?.admin && <Link to="/users">{t("navUsers")}</Link>}
          {user?.admin && <Link to="/moderation">{t("navModeration")}</Link>}
          {user ? <span>{user.name}</span> : <Link to="/login">{t("navLogin")}</Link>}
        </nav>
      </header>
      {children}
    </div>
  );
}
