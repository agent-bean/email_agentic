import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Icon } from "../components/icon";
import { Overview, NewResearch } from "../features/research";
import { ResearchDetail } from "../features/research-detail";
import { Collection, System } from "../features/collections";
import { SentReview } from "../features/sent-review";
import { Inbox } from "../features/inbox";

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => {
    setMenuOpen(false);
    const title =
      location.pathname === "/"
        ? "Tổng quan"
        : location.pathname === "/research/new"
          ? "Nghiên cứu mới"
          : location.pathname.startsWith("/research/")
            ? "Nghiên cứu doanh nghiệp"
            : ({
                "/inputs": "Email & cuộc họp",
                "/sent-review": "Đối chiếu Sent",
                "/companies": "Doanh nghiệp",
                "/knowledge": "Kho tri thức",
                "/system": "Kết nối & vận hành",
              }[location.pathname] ?? "Email Assistant");
    document.title = `${title} · Email Assistant`;
  }, [location.pathname]);
  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Đến nội dung
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
              Email Assistant<small>Research workspace</small>
            </span>
          </Link>
          <button
            ref={menuButton}
            className="nav-toggle secondary"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? "Đóng menu" : "Menu"}
          </button>
        </div>
        <nav
          id="main-navigation"
          aria-label="Điều hướng chính"
          onClick={() => setMenuOpen(false)}
        >
          <p className="nav-label">KHÔNG GIAN LÀM VIỆC</p>
          <NavLink to="/" end>
            <Icon name="overview" />
            Tổng quan
          </NavLink>
          <NavLink to="/research/new">
            <Icon name="research" />
            Nghiên cứu mới
          </NavLink>
          <NavLink to="/inputs">
            <Icon name="inbox" />
            Email & cuộc họp
          </NavLink>
          <NavLink to="/sent-review">
            <Icon name="sent" />
            Đối chiếu Sent
          </NavLink>
          <p className="nav-label">DỮ LIỆU & VẬN HÀNH</p>
          <NavLink to="/companies">
            <Icon name="company" />
            Doanh nghiệp
          </NavLink>
          <NavLink to="/knowledge">
            <Icon name="knowledge" />
            Kho tri thức
          </NavLink>
          <NavLink to="/system">
            <Icon name="system" />
            Kết nối & vận hành
          </NavLink>
        </nav>
        <div className="sidebar-note">
          <Icon name="shield" />
          <strong>Bạn giữ quyền quyết định</strong>
          <p>
            Email và báo cáo chỉ được gửi hoặc lưu vào kho tri thức sau khi bạn
            duyệt.
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
            element={<Collection kind="companies" title="Doanh nghiệp" />}
          />
          <Route
            path="/knowledge"
            element={<Collection kind="knowledge" title="Kho tri thức" />}
          />
          <Route path="/system" element={<System />} />
          <Route
            path="*"
            element={
              <section className="panel empty">
                <h1>Không tìm thấy trang</h1>
                <p>
                  Đường dẫn có thể đã thay đổi. Trở về danh sách nghiên cứu để
                  tiếp tục.
                </p>
                <Link className="button" to="/">
                  Về tổng quan
                </Link>
              </section>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
