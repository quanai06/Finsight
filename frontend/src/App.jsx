import { Link, Outlet } from "react-router-dom";

// App shell: a slim top bar shared across pages.
export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-mark">F</span>
            <span className="brand-name">Finsight</span>
          </Link>
          <span className="topbar-tag">Document Q&amp;A</span>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
