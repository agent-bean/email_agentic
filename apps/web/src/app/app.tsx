import { useRef, useState } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { Overview, NewResearch } from '../features/research';
import { ResearchDetail } from '../features/research-detail';
import { Collection, System } from '../features/collections';
import { SentReview } from '../features/sent-review';
import { Inbox } from '../features/inbox';

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Đến nội dung
      </a>
      <aside
        className={menuOpen ? 'nav-open' : ''}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen) {
            setMenuOpen(false);
            menuButton.current?.focus();
          }
        }}
      >
        <div className="brand-row">
          <Link className="brand" to="/">
            Email<span>Assistant</span>
          </Link>
          <button
            ref={menuButton}
            className="nav-toggle secondary"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? 'Đóng menu' : 'Menu'}
          </button>
        </div>
        <p className="eyebrow">KHÔNG GIAN LÀM VIỆC</p>
        <nav
          id="main-navigation"
          aria-label="Điều hướng chính"
          onClick={() => setMenuOpen(false)}
        >
          <NavLink to="/" end>
            Tổng quan
          </NavLink>
          <NavLink to="/research/new">Nghiên cứu mới</NavLink>
          <NavLink to="/inputs">Email & cuộc họp</NavLink>
          <NavLink to="/sent-review">Đối chiếu Sent</NavLink>
          <NavLink to="/companies">Doanh nghiệp</NavLink>
          <NavLink to="/knowledge">Kho tri thức</NavLink>
          <NavLink to="/system">Kết nối & vận hành</NavLink>
        </nav>
        <div className="sidebar-note">
          Bạn luôn duyệt trước khi gửi email hoặc lưu báo cáo vào kho tri thức.
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
