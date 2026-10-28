import { NavLink, Route, Routes } from 'react-router-dom';
import { Overview, NewResearch } from '../features/research';
import { ResearchDetail } from '../features/research-detail';
import { Collection, System } from '../features/collections';

export function App() {
  return <div className="shell">
    <aside><a className="brand" href="/">Email<span>Assistant</span></a><p className="eyebrow">KHÔNG GIAN LÀM VIỆC</p>
      <nav aria-label="Điều hướng chính">
        <NavLink to="/" end>Tổng quan</NavLink><NavLink to="/research/new">Nghiên cứu mới</NavLink>
        <NavLink to="/inputs">Email & cuộc họp</NavLink><NavLink to="/companies">Doanh nghiệp</NavLink>
        <NavLink to="/knowledge">Tri thức</NavLink><NavLink to="/system">Kết nối & vận hành</NavLink>
      </nav><div className="sidebar-note">Bạn luôn duyệt trước khi gửi email hoặc lưu tri thức chính thức.</div>
    </aside>
    <main><Routes>
      <Route path="/" element={<Overview />} /><Route path="/research/new" element={<NewResearch />} />
      <Route path="/research/:id" element={<ResearchDetail />} />
      <Route path="/inputs" element={<Collection kind="inputs" title="Email & cuộc họp" />} />
      <Route path="/companies" element={<Collection kind="companies" title="Doanh nghiệp" />} />
      <Route path="/knowledge" element={<Collection kind="knowledge" title="Tri thức" />} />
      <Route path="/system" element={<System />} />
      <Route path="*" element={<h1>Không tìm thấy trang</h1>} />
    </Routes></main>
  </div>;
}
