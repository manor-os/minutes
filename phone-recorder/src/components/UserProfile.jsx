import React, { useState } from "react";
import Settings from "./Settings";
import UsageStats from "./UsageStats";
import "./UserProfile.css";

function UserProfile({ user, onLogout, onUserUpdate, showSettings: externalShowSettings, onSettingsClose }) {
  const [isOpen, setIsOpen] = useState(false);
  const [internalShowSettings, setInternalShowSettings] = useState(false);
  const [showUsage, setShowUsage] = useState(false);

  const showSettings = externalShowSettings || internalShowSettings;
  const setShowSettings = (val) => {
    setInternalShowSettings(val);
    if (!val && onSettingsClose) onSettingsClose();
  };

  if (!user) return null;

  return (
    <div className="user-profile-container quiet-profile">
      <button
        className="user-profile-trigger"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="User profile"
        aria-expanded={isOpen}
      >
        <div className="user-avatar">
          {user.name
            ? user.name.charAt(0).toUpperCase()
            : user.email?.charAt(0).toUpperCase() || "U"}
        </div>
      </button>

      {isOpen && (
        <>
          <div className="profile-overlay" onClick={() => setIsOpen(false)} />
          <div className="user-profile-dropdown">
            <div className="profile-header">
              <div className="profile-details">
                <h3 className="profile-name">{user.name || "User"}</h3>
                {user.email && <p className="profile-email">{user.email}</p>}
              </div>
            </div>

            <div className="profile-divider"></div>

            <div className="profile-menu">
              <button
                className="profile-menu-item"
                onClick={() => {
                  setIsOpen(false);
                  setShowSettings(true);
                }}
              >
                <span>Settings</span>
              </button>
              <button
                className="profile-menu-item"
                onClick={() => {
                  setIsOpen(false);
                  setShowUsage(true);
                }}
              >
                <span>Usage</span>
              </button>
              <a
                className="profile-menu-item"
                href="https://manor-os.github.io/docs/minutes/"
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setIsOpen(false)}
              >
                <span>Documentation</span>
              </a>
            </div>

            <div className="profile-divider"></div>

            <button
              className="profile-logout-btn"
              onClick={() => {
                setIsOpen(false);
                if (onLogout) {
                  onLogout();
                }
              }}
            >
              <span>Logout</span>
            </button>
          </div>
        </>
      )}

      {showSettings && (
        <Settings
          user={user}
          onClose={() => {
            setShowSettings(false);
          }}
          onUpdate={(updatedUser) => {
            if (onUserUpdate) {
              onUserUpdate(updatedUser);
            }
          }}
        />
      )}

      {showUsage && <UsageStats onClose={() => setShowUsage(false)} />}
    </div>
  );
}

export default UserProfile;
