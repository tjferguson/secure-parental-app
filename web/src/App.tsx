import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { configureAuth, getCurrentUser, signOut as authSignOut, AuthUser } from './services/auth';
import { config } from './config';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ChatDashboard from './pages/ChatDashboard';
import ChatPage from './pages/ChatPage';

// ---------------------------------------------------------------------------
// Auth Context
// ---------------------------------------------------------------------------

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
  setUser: (u: AuthUser | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signOut: async () => {},
  setUser: () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

// ---------------------------------------------------------------------------
// Protected Route
// ---------------------------------------------------------------------------

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    configureAuth();

    getCurrentUser()
      .then((u) => {
        setUser(u);
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  async function handleSignOut() {
    await authSignOut();
    setUser(null);
    navigate('/login');
  }

  // Auto-sign-in for local dev mode
  useEffect(() => {
    if (config.localDev && !user && !loading) {
      getCurrentUser().then(setUser).catch(() => {});
    }
  }, [loading, user]);

  return (
    <AuthContext.Provider
      value={{ user, loading, signOut: handleSignOut, setUser }}
    >
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/chat/:childId"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthContext.Provider>
  );
}
