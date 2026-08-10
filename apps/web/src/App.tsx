import { NavLink, Route, Routes } from "react-router-dom";
import AskPage from "./pages/AskPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentsPage from "./pages/DocumentsPage";

export default function App() {
  return (
    <div className="app-shell">
      <nav className="topnav">
        <div className="brand">Arabic PDF RAG</div>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : undefined)}>
          Documents
        </NavLink>
        <NavLink to="/ask" className={({ isActive }) => (isActive ? "active" : undefined)}>
          Ask
        </NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<DocumentsPage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/document/:id" element={<DocumentDetailPage />} />
      </Routes>
    </div>
  );
}
