import { useState } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { Overview, NewResearch } from '../features/research';
import { ResearchDetail } from '../features/research-detail';
import { Collection, System } from '../features/collections';
import { Inbox } from '../features/inbox';

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return <div className="shell"><a className="skip-link" href="#main-content">Đến nội dung</a>
    <aside className={menuOpen ? 'nav-open' : ''}><div className="brand-row"><Link className="brand" to="/">Email<span>Assistant</span></Link><button className="nav-toggle secondary" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? 'Đóng menu' : 'Menu'}</button></div><p className="eyebrow">KHÔNG GIAN LÀM VIỆC</p>
      <nav id="main-navigation" aria-label="Điều hướng chính" onClick={() => setMenuOpen(false)}>
        <NavLink to="/" end>Tổng quan</NavLink><NavLink to="/research/new">Nghiên cứu mới</NavLink>
        <NavLink to="/inputs">Email & cuộc họp</NavLink><NavLink to="/companies">Doanh nghiệp</NavLink>
        <NavLink to="/knowledge">Kho tri thức</NavLink><NavLink to="/system">Kết nối & vận hành</NavLink>
      </nav><div className="sidebar-note">Bạn luôn duyệt trước khi gửi email hoặc lưu báo cáo vào kho tri thức.</div>
    </aside>
    <main id="main-content"><Routes>
      <Route path="/" element={<Overview />} /><Route path="/research/new" element={<NewResearch />} />
      <Route path="/research/:id" element={<ResearchDetail />} />
      <Route path="/inputs" element={<Inbox />} />
      <Route path="/companies" element={<Collection kind="companies" title="Doanh nghiệp" />} />
      <Route path="/knowledge" element={<Collection kind="knowledge" title="Kho tri thức" />} />
      <Route path="/system" element={<System />} />
      <Route path="*" element={<h1>Không tìm thấy trang</h1>} />
    </Routes></main>
  </div>;
}
