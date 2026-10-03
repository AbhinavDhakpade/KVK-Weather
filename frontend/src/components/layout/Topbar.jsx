import { useLocation } from "react-router-dom";
import { useAppSettings } from "../../context/AppSettingsContext";
import { useAppData } from "../../context/DataContext";
import { useAuth } from "../../context/AuthContext";

const PAGE_KEY_BY_PATH = {
  "/": "dashboard",
  "/weather": "weather",
  "/disease": "disease",
  "/irrigation": "irrigation",
  "/forecast": "forecast",
  "/alerts": "alerts",
  "/gdd": "gdd",
  "/farm": "farm",
};

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "mr", label: "MR" },
  { code: "hi", label: "HI" },
];

export default function Topbar() {
  const { toggleSidebar, lang, setLang, dark, toggleDark, t } = useAppSettings();
  const { refresh, loading } = useAppData();
  const location = useLocation();
    const { user, logout } = useAuth();

  const pageKey = PAGE_KEY_BY_PATH[location.pathname] || "dashboard";

  return (
    <div className="topbar">
      <button className="topbar-toggle" onClick={toggleSidebar} title="Toggle sidebar" aria-label="Toggle sidebar">
        ☰
      </button>
      <div className="topbar-title">{t(`pageTitles.${pageKey}`)}</div>
      <div className="topbar-chips">
        {LANGUAGES.map((l) => (
          <div
            key={l.code}
            className={`chip${lang === l.code ? " active" : ""}`}
            onClick={() => setLang(l.code)}
          >
            {l.label}
          </div>
        ))}
      </div>
      <div className="topbar-actions">
        <button className="icon-btn" onClick={toggleDark} title="Dark Mode" aria-label="Toggle dark mode">
          🌙
        </button>
        <button
          className="icon-btn"
          onClick={refresh}
          title="Refresh"
          aria-label="Refresh data"
          style={{
            transform: loading ? "rotate(360deg)" : "none",
            transition: "transform 0.6s",
          }}
        >
          🔄
        </button>
                <button className="icon-btn" onClick={logout} title={`Log out (${user?.username})`} aria-label="Log out">
          🚪
        </button>
      </div>
    </div>
  );
}
