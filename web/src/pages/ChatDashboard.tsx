import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getChildren, Child } from '../services/api';
import { useAuth } from '../App';
import RegistrationCodeModal from '../components/RegistrationCodeModal';

export default function ChatDashboard() {
  const [children, setChildren] = useState<Child[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  useEffect(() => {
    fetchChildren();
  }, []);

  async function fetchChildren() {
    try {
      const data = await getChildren();
      setChildren(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load children.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleChildClick(childId: string) {
    navigate(`/chat/${childId}`);
  }

  function handleModalClose() {
    setModalOpen(false);
    fetchChildren();
  }

  return (
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2 className="sidebar-logo">ParentChat</h2>
          <span className="sidebar-email">{user?.email}</span>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-title">Children</div>

          {loading && (
            <div className="sidebar-loading">
              <div className="spinner-sm" />
            </div>
          )}

          {!loading && error && <div className="sidebar-error">{error}</div>}

          {!loading && !error && children.length === 0 && (
            <div className="sidebar-empty">
              <p>No children registered yet.</p>
              <p className="sidebar-empty-hint">
                Click &ldquo;Add Child&rdquo; to get started.
              </p>
            </div>
          )}

          {children.map((child) => (
            <button
              key={child.childId}
              className="sidebar-child-card"
              onClick={() => handleChildClick(child.childId)}
            >
              <div className="child-avatar">
                {child.displayName.charAt(0).toUpperCase()}
              </div>
              <div className="child-info">
                <span className="child-name">{child.displayName}</span>
                <span className="child-registered">
                  Joined {new Date(child.registeredAt).toLocaleDateString()}
                </span>
              </div>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            className="btn btn-primary btn-full"
            onClick={() => setModalOpen(true)}
          >
            + Add Child
          </button>
          <button className="btn btn-secondary btn-full" onClick={signOut}>
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main area */}
      <main className="dashboard-main">
        <div className="dashboard-welcome">
          <h1>Welcome to ParentChat</h1>
          <p>Select a child from the sidebar to start chatting, or add a new child.</p>

          {!loading && children.length === 0 && (
            <div className="dashboard-empty-cta">
              <p>Get started by registering your first child device.</p>
              <button
                className="btn btn-primary"
                onClick={() => setModalOpen(true)}
              >
                + Add Child
              </button>
            </div>
          )}

          {!loading && children.length > 0 && (
            <div className="dashboard-children-grid">
              {children.map((child) => (
                <button
                  key={child.childId}
                  className="dashboard-child-tile"
                  onClick={() => handleChildClick(child.childId)}
                >
                  <div className="tile-avatar">
                    {child.displayName.charAt(0).toUpperCase()}
                  </div>
                  <div className="tile-name">{child.displayName}</div>
                  <div className="tile-date">
                    Joined {new Date(child.registeredAt).toLocaleDateString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Registration modal */}
      <RegistrationCodeModal isOpen={modalOpen} onClose={handleModalClose} />
    </div>
  );
}
