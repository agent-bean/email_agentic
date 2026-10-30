import { I18nProvider, useI18n } from "../lib/i18n";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Icon } from "../components/icon";
import { Overview, NewResearch } from "../features/research";
import { ResearchDetail } from "../features/research-detail";
import { Collection, System } from "../features/collections";
import { SentReview } from "../features/sent-review";
import { Inbox } from "../features/inbox";
import { Knowledge } from "../features/knowledge";

export function App() {
  return <I18nProvider><Workspace /></I18nProvider>;
}

function Workspace() {
  const { t, language, setLanguage } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => {
    setMenuOpen(false);
    const title =
      location.pathname === "/"
        ? t("Tổng quan", "Overview")
        : location.pathname === "/research/new"
          ? t("Nghiên cứu mới", "New research")
          : location.pathname.startsWith("/research/")
            ? t("Nghiên cứu doanh nghiệp", "Company research")
            : ({
                "/inputs": new URLSearchParams(location.search).get("kind") === "calendar" ? t("Cuộc họp", "Meetings") : t("Email đến", "Incoming email"),
                "/sent-review": t("Lịch sử gửi email", "Email sending history"),
                "/companies": t("Doanh nghiệp", "Companies"),
                "/knowledge": t("Kho tri thức", "Knowledge library"),
                "/system": t("Kết nối & vận hành", "Connections & operations"),
              }[location.pathname] ?? "Email Assistant");
    document.title = `${title} · Email Assistant`;
  }, [location.pathname, location.search, language]);
  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        {t("Đến nội dung", "Skip to content")}
      </a>
      <aside
        className={menuOpen ? "nav-open" : ""}
        onKeyDown={(event) => {
          if (event.key === "Escape" && menuOpen) {
            setMenuOpen(false);
            menuButton.current?.focus();
          }
        }}
      >
        <div className="brand-row">
          <Link className="brand" to="/">
            <span className="brand-mark" aria-hidden="true">
              ea<span>.</span>
            </span>
            <span className="brand-name">
              Email Assistant<small>{t("Không gian làm việc", "Workspace")}</small>
            </span>
          </Link>
          <button
            ref={menuButton}
            className="nav-toggle secondary"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? t("Đóng menu", "Close menu") : "Menu"}
          </button>
        </div>
        <label className="language-picker">
          <span>{t("Ngôn ngữ", "Language")}</span>
          <select value={language} onChange={(event) => setLanguage(event.currentTarget.value === "en" ? "en" : "vi")}>
            <option value="vi" lang="vi">Tiếng Việt</option>
            <option value="en" lang="en">English</option>
          </select>
        </label>
        <nav
          id="main-navigation"
          aria-label={t("Điều hướng chính", "Main navigation")}
          onClick={() => setMenuOpen(false)}
        >
          <p className="nav-label">{t("KHÔNG GIAN LÀM VIỆC", "WORKSPACE")}</p>
          <NavLink to="/" end>
            <Icon name="overview" />
            {t("Tổng quan", "Overview")}
          </NavLink>
          <NavLink to="/research/new">
            <Icon name="research" />
            {t("Nghiên cứu mới", "New research")}
          </NavLink>
          <Link to="/inputs?kind=email" className={location.pathname === "/inputs" && new URLSearchParams(location.search).get("kind") !== "calendar" ? "active" : undefined} aria-current={location.pathname === "/inputs" && new URLSearchParams(location.search).get("kind") !== "calendar" ? "page" : undefined}>
            <Icon name="inbox" />
            {t("Email đến", "Incoming email")}
          </Link>
          <Link to="/inputs?kind=calendar" className={location.pathname === "/inputs" && new URLSearchParams(location.search).get("kind") === "calendar" ? "active" : undefined} aria-current={location.pathname === "/inputs" && new URLSearchParams(location.search).get("kind") === "calendar" ? "page" : undefined}>
            <Icon name="calendar" />
            {t("Cuộc họp", "Meetings")}
          </Link>
          <NavLink to="/sent-review">
            <Icon name="sent" />
            {t("Lịch sử gửi email", "Email sending history")}
          </NavLink>
          <p className="nav-label">{t("DỮ LIỆU & VẬN HÀNH", "DATA & OPERATIONS")}</p>
          <NavLink to="/companies">
            <Icon name="company" />
            {t("Doanh nghiệp", "Companies")}
          </NavLink>
          <NavLink to="/knowledge">
            <Icon name="knowledge" />
            {t("Kho tri thức", "Knowledge library")}
          </NavLink>
          <NavLink to="/system">
            <Icon name="system" />
            {t("Kết nối & vận hành", "Connections & operations")}
          </NavLink>
        </nav>
        <div className="sidebar-note">
          <Icon name="shield" />
          <strong>{t("Bạn giữ quyền quyết định", "You stay in control")}</strong>
          <p>
            {t("Email và báo cáo chỉ được gửi hoặc lưu vào kho tri thức sau khi bạn duyệt.", "Emails and reports are sent or saved to the knowledge library only after your approval.")}
          </p>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/research/new" element={<NewResearch />} />
          <Route path="/research/:id" element={<ResearchDetail />} />
          <Route path="/inputs" element={<Inbox />} />
          <Route path="/sent-review" element={<SentReview />} />
          <Route
            path="/companies"
            element={<Collection kind="companies" title={t("Doanh nghiệp", "Companies")} />}
          />
          <Route
            path="/knowledge"
            element={<Knowledge />}
          />
          <Route path="/system" element={<System />} />
          <Route
            path="*"
            element={
              <section className="panel empty">
                <h1>{t("Không tìm thấy trang", "Page not found")}</h1>
                <p>
                  {t("Đường dẫn có thể đã thay đổi. Trở về danh sách nghiên cứu để tiếp tục.", "This address may have changed. Return to your research to continue.")}
                </p>
                <Link className="button" to="/">
                  {t("Về tổng quan", "Back to overview")}
                </Link>
              </section>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
