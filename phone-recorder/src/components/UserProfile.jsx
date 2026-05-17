import React, { useState } from "react";
import Settings from "./Settings";
import UsageStats from "./UsageStats";
import { SettingsIcon, BarChartIcon, LogOutIcon, FileTextIcon } from "./Icons";
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
    <div className="user-profile-container">
      <button
        className="user-profile-trigger"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="User profile"
      >
        <div className="user-avatar">
          {user.name
            ? user.name.charAt(0).toUpperCase()
            : user.email?.charAt(0).toUpperCase() || "U"}
        </div>
        <div className="user-info-inline">
          <span className="user-name">{user.name || "User"}</span>
          <span className="user-email">
            {user.email || `Entity ID: ${user.entity_id}`}
          </span>
        </div>
        <svg
          className={`profile-arrow ${isOpen ? "open" : ""}`}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
        >
          <path
            d="M3 4.5L6 7.5L9 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {isOpen && (
        <>
          <div className="profile-overlay" onClick={() => setIsOpen(false)} />
          <div className="user-profile-dropdown">
            <div className="profile-header">
              <div className="profile-avatar-large">
                {user.name
                  ? user.name.charAt(0).toUpperCase()
                  : user.email?.charAt(0).toUpperCase() || "U"}
              </div>
              <div className="profile-details">
                <h3 className="profile-name">{user.name || "User"}</h3>
                <p className="profile-email">
                  {user.email || `Entity ID: ${user.entity_id}`}
                </p>
                {user.entity_id && (
                  <p className="profile-entity-id">
                    Entity ID: {user.entity_id}
                  </p>
                )}
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
                <SettingsIcon size={16} className="menu-icon-svg" />
                <span>Settings</span>
              </button>
              <button
                className="profile-menu-item"
                onClick={() => {
                  setIsOpen(false);
                  setShowUsage(true);
                }}
              >
                <BarChartIcon size={16} className="menu-icon-svg" />
                <span>Usage Statistics</span>
              </button>
              <a
                className="profile-menu-item"
                href="https://manor-os.github.io/docs/minutes/"
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setIsOpen(false)}
              >
                <FileTextIcon size={16} className="menu-icon-svg" />
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
              <LogOutIcon size={16} className="menu-icon-svg" />
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
