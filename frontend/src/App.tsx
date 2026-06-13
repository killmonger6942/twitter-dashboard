import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Users, PenSquare, List, UserCircle, LogOut } from 'lucide-react';
import Accounts from './pages/Accounts';
import Compose from './pages/Compose';
import Queue from './pages/Queue';
import Personas from './pages/Personas';
import LoginPage from './components/LoginPage';
import { api, getToken, clearToken } from './lib/api';

function NavItem({ to, icon: Icon, label }: { to: string; icon: any; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
          isActive ? 'bg-blue-600 text-white' : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
        }`
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  );
}

function Dashboard() {
  const handleLogout = () => {
    clearToken();
    window.location.reload();
  };

  return (
    <BrowserRouter>
      <div className="min-h-screen flex">
        <nav className="w-56 bg-neutral-900 border-r border-neutral-800 p-4 flex flex-col gap-1">
          <h1 className="text-lg font-bold text-white mb-6 px-2">Twitter Dashboard</h1>
          <NavItem to="/" icon={Users} label="Accounts" />
          <NavItem to="/personas" icon={UserCircle} label="Personas" />
          <NavItem to="/compose" icon={PenSquare} label="Compose" />
          <NavItem to="/queue" icon={List} label="Queue" />
          <div className="mt-auto pt-4 border-t border-neutral-800">
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-neutral-400 hover:text-white hover:bg-neutral-800 w-full transition-colors"
            >
              <LogOut size={18} />
              Logout
            </button>
          </div>
        </nav>
        <main className="flex-1 p-8 overflow-auto">
          <Routes>
            <Route path="/" element={<Accounts />} />
            <Route path="/personas" element={<Personas />} />
            <Route path="/compose" element={<Compose />} />
            <Route path="/queue" element={<Queue />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setAuthed(false);
      return;
    }
    api.auth.me()
      .then(() => setAuthed(true))
      .catch(() => {
        clearToken();
        setAuthed(false);
      });
  }, []);

  if (authed === null) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="text-neutral-400 text-sm">Loading...</div>
      </div>
    );
  }

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />;
  }

  return <Dashboard />;
}
