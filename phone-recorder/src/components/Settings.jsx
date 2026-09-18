import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { CloseIcon } from "./Icons";
import { IS_CLOUD, IS_COMMUNITY } from "../config/edition";
import "./Settings.css";
import "./QuietForms.css";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";
const STT_MODE = import.meta.env.VITE_STT_MODE || "cloud";
const LLM_MODE = import.meta.env.VITE_LLM_MODE || "cloud";

function Settings({ user, onClose, onUpdate }) {
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [formData, setFormData] = useState({
    name: user?.name || "",
    email: user?.email || "",
    notifications: true,
    autoRefresh: true,
    refreshInterval: 5,
    transcriptLanguage: "",
  });
  const [sttApiKey, setSttApiKey] = useState("");
  const [sttBaseUrl, setSttBaseUrl] = useState("");
  const [showSttKey, setShowSttKey] = useState(false);
  const [hasSttKey, setHasSttKey] = useState(false);
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [showLlmKey, setShowLlmKey] = useState(false);
  const [hasLlmKey, setHasLlmKey] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [sttPolicy, setSttPolicy] = useState(IS_CLOUD ? "manor" : null);
  const [llmPolicy, setLlmPolicy] = useState(IS_CLOUD ? "manor" : null);
  const [policyVerified, setPolicyVerified] = useState(false);

  // Webhook notification state
  const [webhookUrl, setWebhookUrl] = useState("");

  // Account management state (local auth only)
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    // Load saved preferences from localStorage
    const savedName = localStorage.getItem("user_name") || user?.name || "";
    const savedEmail = localStorage.getItem("user_email") || user?.email || "";
    const savedNotifications =
      localStorage.getItem("notifications_enabled") !== "false";
    const savedAutoRefresh =
      localStorage.getItem("auto_refresh_enabled") !== "false";
    const savedRefreshInterval = parseInt(
      localStorage.getItem("refresh_interval") || "5",
      10,
    );
    const savedLanguage = localStorage.getItem("transcript_language") || "";

    setFormData({
      name: savedName,
      email: savedEmail,
      notifications: savedNotifications,
      autoRefresh: savedAutoRefresh,
      refreshInterval: savedRefreshInterval,
      transcriptLanguage: savedLanguage,
    });

    // Load AI config
    const savedModel = localStorage.getItem("llm_model") || "";
    const savedBaseUrl = localStorage.getItem("llm_base_url") || "";
    const savedSttBaseUrl = localStorage.getItem("stt_base_url") || "";
    setLlmModel(savedModel);
    setLlmBaseUrl(savedBaseUrl);
    setSttBaseUrl(savedSttBaseUrl);
    setHasSttKey(localStorage.getItem("has_stt_key") === "true");
    setHasLlmKey(localStorage.getItem("has_llm_key") === "true");

    // Try to load from backend
    const token = localStorage.getItem("auth_token");
    if (token) {
      fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.success) {
            setPolicyVerified(
              ["manor", "local"].includes(data.stt_managed_by) &&
              ["manor", "local"].includes(data.llm_managed_by),
            );
            const policy = data.stt_managed_by || data.llm_managed_by;
            if (policy === "manor" || policy === "local") {
              setSttPolicy(policy);
            }
            if (data.llm_managed_by === "manor" || data.llm_managed_by === "local") {
              setLlmPolicy(data.llm_managed_by);
            }
            if (data.llm_model) setLlmModel(data.llm_model);
            if (data.llm_base_url) setLlmBaseUrl(data.llm_base_url);
            if (data.stt_base_url !== undefined)
              setSttBaseUrl(data.stt_base_url);
            setHasSttKey(!!data.has_stt_key);
            setHasLlmKey(!!data.has_llm_key);
            if (data.webhook_url) setWebhookUrl(data.webhook_url);
          }
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount, not when user changes

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
    // Clear messages when user starts typing
    setSuccessMessage("");
    setErrorMessage("");
  };

  const handleSave = async () => {
    setIsLoading(true);
    setSuccessMessage("");
    setErrorMessage("");

    try {
      // Save preferences to localStorage
      localStorage.setItem("user_name", formData.name);
      localStorage.setItem("user_email", formData.email);
      localStorage.setItem(
        "notifications_enabled",
        formData.notifications.toString(),
      );
      localStorage.setItem(
        "auto_refresh_enabled",
        formData.autoRefresh.toString(),
      );
      localStorage.setItem(
        "refresh_interval",
        formData.refreshInterval.toString(),
      );
      localStorage.setItem(
        "transcript_language",
        formData.transcriptLanguage || "",
      );

      // If name or email changed, update user object
      if (onUpdate) {
        onUpdate({
          ...user,
          name: formData.name || user?.name,
          email: formData.email || user?.email,
        });
      }

      // Save AI config to backend (if any keys or model changed)
      if (sttPolicy === "local" || llmPolicy === "local") {
        await handleSaveLlmConfig(true);
      }

      // Save webhook URL to backend
      const token = localStorage.getItem("auth_token");
      if (token) {
        try {
          await fetch(`${API_BASE_URL}/api/auth/webhook`, {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ webhook_url: webhookUrl }),
          });
        } catch (e) {
          console.warn("Failed to save webhook URL:", e);
        }
      }

      setSuccessMessage("Settings saved successfully!");
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (error) {
      console.error("Error saving settings:", error);
      setErrorMessage("Failed to save settings. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setFormData({
      name: user?.name || "",
      email: user?.email || "",
      notifications: true,
      autoRefresh: true,
      refreshInterval: 5,
    });
    setSuccessMessage("");
    setErrorMessage("");
  };

  const handleSaveLlmConfig = async (silent = false) => {
    setLlmSaving(true);
    setErrorMessage("");
    try {
      const token = localStorage.getItem("auth_token");
      const body = {};
      if (sttPolicy === "local" && STT_MODE !== "local") {
        if (sttApiKey) body.stt_api_key = sttApiKey;
        if (sttBaseUrl !== undefined) body.stt_base_url = sttBaseUrl;
      }
      if (llmPolicy === "local" && LLM_MODE !== "local") {
        if (llmApiKey) body.llm_api_key = llmApiKey;
        if (llmModel !== undefined) body.llm_model = llmModel;
        if (llmBaseUrl !== undefined) body.llm_base_url = llmBaseUrl;
      }

      if (Object.keys(body).length === 0) return;

      const res = await fetch(`${API_BASE_URL}/api/auth/llm-config`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        localStorage.setItem("llm_model", llmModel);
        localStorage.setItem("llm_base_url", llmBaseUrl);
        localStorage.setItem("stt_base_url", sttBaseUrl);
        if (sttApiKey) {
          setHasSttKey(true);
          localStorage.setItem("has_stt_key", "true");
          setSttApiKey("");
        }
        if (llmApiKey) {
          setHasLlmKey(true);
          localStorage.setItem("has_llm_key", "true");
          setLlmApiKey("");
        }
        localStorage.removeItem("stt_api_key");
        window.dispatchEvent(new Event("minutes-ai-config-updated"));
        if (!silent) {
          setSuccessMessage("AI configuration saved!");
          setTimeout(() => setSuccessMessage(""), 3000);
        }
      } else {
        const data = await res.json().catch(() => ({}));
        if (!silent)
          setErrorMessage(data.detail || "Failed to save AI configuration");
      }
    } catch (e) {
      setErrorMessage("Failed to save. Check your connection.");
    } finally {
      setLlmSaving(false);
    }
  };

  const handleChangePassword = async () => {
    setErrorMessage("");
    setSuccessMessage("");
    if (!currentPassword || !newPassword) {
      setErrorMessage("Please fill in all password fields.");
      return;
    }
    if (newPassword.length < 6) {
      setErrorMessage("New password must be at least 6 characters.");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setErrorMessage("New passwords do not match.");
      return;
    }
    setPasswordSaving(true);
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API_BASE_URL}/api/auth/change-password`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setSuccessMessage("Password changed successfully!");
        setCurrentPassword("");
        setNewPassword("");
        setConfirmNewPassword("");
        setTimeout(() => setSuccessMessage(""), 3000);
      } else {
        setErrorMessage(data.detail || "Failed to change password.");
      }
    } catch {
      setErrorMessage("Failed to change password. Check your connection.");
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleDeleteAccount = async () => {
    setErrorMessage("");
    if (!deletePassword) {
      setErrorMessage("Please enter your password to confirm deletion.");
      return;
    }
    setDeleteLoading(true);
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API_BASE_URL}/api/auth/account`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ password: deletePassword }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        // Clear all local storage and redirect to login
        localStorage.clear();
        window.location.reload();
      } else {
        setErrorMessage(data.detail || "Failed to delete account.");
      }
    } catch {
      setErrorMessage("Failed to delete account. Check your connection.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const LLM_MODELS = [
    { value: "", label: "Default (server setting)" },
    { value: "gpt4o", label: "GPT-4o (OpenAI)" },
    { value: "gpt4o-mini", label: "GPT-4o Mini (OpenAI)" },
    { value: "claude-sonnet", label: "Claude Sonnet (Anthropic)" },
    { value: "claude-opus", label: "Claude Opus (Anthropic)" },
    { value: "gemini", label: "Gemini Pro (Google)" },
    { value: "gemini-flash", label: "Gemini Flash (Google)" },
    { value: "deepseek", label: "DeepSeek Chat" },
    { value: "kimi", label: "Kimi K2.5 (Moonshot)" },
  ];

  const modalContent = (
    <div className="settings-modal quiet-settings" onClick={onClose}>
      <div
        className="settings-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-header">
          <h2 id="settings-title">Settings</h2>
          <button
            className="settings-close-btn"
            onClick={onClose}
            aria-label="Close settings"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <div className="settings-body">
          {/* Profile Section */}
          <div className="settings-section">
            <div className="settings-form">
              <div className="form-group">
                <label htmlFor="name">Name</label>
                <input
                  id="name"
                  name="name"
                  type="text"
                  value={formData.name}
                  onChange={handleInputChange}
                  placeholder="Enter your display name"
                />
              </div>

              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  placeholder="Enter your email"
                  disabled
                />
              </div>
            </div>
          </div>

          <div className="settings-section quiet-language">
            <div className="settings-form">
              <div className="form-group">
                <label htmlFor="transcriptLanguage">Transcript language</label>
                <select
                  id="transcriptLanguage"
                  value={formData.transcriptLanguage || ""}
                  onChange={handleInputChange}
                  name="transcriptLanguage"
                  className="form-select"
                >
                  <option value="">Auto-detect</option>
                  <option value="en">English</option>
                  <option value="zh">中文 (Chinese)</option>
                  <option value="ja">日本語 (Japanese)</option>
                  <option value="ko">한국어 (Korean)</option>
                  <option value="es">Español (Spanish)</option>
                  <option value="fr">Français (French)</option>
                  <option value="de">Deutsch (German)</option>
                  <option value="pt">Português (Portuguese)</option>
                  <option value="ar">العربية (Arabic)</option>
                  <option value="ru">Русский (Russian)</option>
                  <option value="it">Italiano (Italian)</option>
                  <option value="nl">Nederlands (Dutch)</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="th">ไทย (Thai)</option>
                  <option value="vi">Tiếng Việt (Vietnamese)</option>
                  <option value="id">Bahasa Indonesia</option>
                  <option value="tr">Türkçe (Turkish)</option>
                  <option value="pl">Polski (Polish)</option>
                  <option value="uk">Українська (Ukrainian)</option>
                  <option value="sv">Svenska (Swedish)</option>
                </select>
              </div>
            </div>
            {policyVerified && sttPolicy === "manor" && llmPolicy === "manor" && (
              <p className="quiet-managed-note">Manor manages transcription and summaries.</p>
            )}
            {policyVerified && sttPolicy === "manor" && llmPolicy !== "manor" && (
              <p className="quiet-managed-note">Manor manages transcription.</p>
            )}
            {policyVerified && llmPolicy === "manor" && sttPolicy !== "manor" && (
              <p className="quiet-managed-note">Manor manages summaries.</p>
            )}
          </div>

          {/* Preferences Section */}
          <details className="settings-section quiet-disclosure">
            <summary>Preferences</summary>
            <div className="settings-form">
              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    name="notifications"
                    checked={formData.notifications}
                    onChange={handleInputChange}
                  />
                  <span className="checkbox-text">
                    <strong>Meeting notifications</strong>
                  </span>
                </label>
              </div>

              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    name="autoRefresh"
                    checked={formData.autoRefresh}
                    onChange={handleInputChange}
                  />
                  <span className="checkbox-text">
                    <strong>Auto-refresh meetings</strong>
                  </span>
                </label>
              </div>

              {formData.autoRefresh && (
                <div className="form-group">
                  <label htmlFor="refreshInterval">
                    Refresh Interval (seconds)
                  </label>
                  <input
                    id="refreshInterval"
                    name="refreshInterval"
                    type="number"
                    min="3"
                    max="60"
                    value={formData.refreshInterval}
                    onChange={handleInputChange}
                  />
                  <p className="form-help">
                    Between 3 and 60 seconds.
                  </p>
                </div>
              )}
            </div>
          </details>

          {sttPolicy !== "manor" && (
            <details className="settings-section quiet-disclosure">
              <summary>Transcription provider</summary>
              <div className="settings-form">
                {sttPolicy === null ? (
                <p>Transcription settings are unavailable until your account policy is verified.</p>
              ) : STT_MODE === "local" ? (
                <div className="settings-info-card">
                  <strong>Local Mode Active</strong>
                  <p>
                    Using faster-whisper (
                    {import.meta.env.VITE_WHISPER_MODEL || "base"} model)
                    running on your machine. No API key or internet required.
                  </p>
                </div>
              ) : (
                <>
                  <div className="form-group">
                    <label htmlFor="sttApiKey">
                      OpenAI API Key
                      {hasSttKey && (
                        <span className="key-badge">✓ Configured</span>
                      )}
                    </label>
                    <div className="input-with-toggle">
                      <input
                        id="sttApiKey"
                        type={showSttKey ? "text" : "password"}
                        value={sttApiKey}
                        onChange={(e) => setSttApiKey(e.target.value)}
                        placeholder={
                          hasSttKey
                            ? "••••••••  (enter new to replace)"
                            : "sk-... (OpenAI key for Whisper)"
                        }
                      />
                      <button
                        type="button"
                        className="toggle-visibility"
                        onClick={() => setShowSttKey(!showSttKey)}
                      >
                        {showSttKey ? "Hide" : "Show"}
                      </button>
                    </div>
                    <p className="form-help">
                      Used for Whisper speech-to-text. Get yours at
                      platform.openai.com
                    </p>
                  </div>

                  <div className="form-group">
                    <label htmlFor="sttBaseUrl">
                      STT API Base URL (optional)
                    </label>
                    <input
                      id="sttBaseUrl"
                      type="url"
                      value={sttBaseUrl}
                      onChange={(e) => setSttBaseUrl(e.target.value)}
                      placeholder="https://openrouter.ai/api/v1 (leave empty for default)"
                    />
                    <p className="form-help">
                      Custom endpoint for Whisper. Use if your STT key is from a
                      proxy service.
                    </p>
                  </div>
                </>
              )}
              </div>
            </details>
          )}

          {llmPolicy !== "manor" && (
            <details className="settings-section quiet-disclosure">
              <summary>Summary provider</summary>
              <div className="settings-form">
                {llmPolicy === null ? (
                <p>Independent model settings are unavailable until your account policy is verified.</p>
              ) : LLM_MODE === "local" ? (
                <div className="settings-info-card">
                  <strong>Local Mode Active</strong>
                  <p>
                    Using {import.meta.env.VITE_OLLAMA_MODEL || "qwen2.5:3b"}{" "}
                    via Ollama running on your machine. Free, private, no
                    internet required.
                  </p>
                </div>
              ) : (
                <>
                  <div className="form-group">
                    <label htmlFor="llmModel">Model</label>
                    <select
                      id="llmModel"
                      value={llmModel}
                      onChange={(e) => setLlmModel(e.target.value)}
                      className="form-select"
                    >
                      {LLM_MODELS.map((m) => (
                        <option key={m.value} value={m.value}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                    <p className="form-help">
                      AI model for generating summaries and action items
                    </p>
                  </div>

                  <div className="form-group">
                    <label htmlFor="llmApiKey">
                      LLM API Key
                      {hasLlmKey && (
                        <span className="key-badge">✓ Configured</span>
                      )}
                    </label>
                    <div className="input-with-toggle">
                      <input
                        id="llmApiKey"
                        type={showLlmKey ? "text" : "password"}
                        value={llmApiKey}
                        onChange={(e) => setLlmApiKey(e.target.value)}
                        placeholder={
                          hasLlmKey
                            ? "••••••••  (enter new to replace)"
                            : "API key for your chosen model"
                        }
                      />
                      <button
                        type="button"
                        className="toggle-visibility"
                        onClick={() => setShowLlmKey(!showLlmKey)}
                      >
                        {showLlmKey ? "Hide" : "Show"}
                      </button>
                    </div>
                    <p className="form-help">
                      Key for the summarization model. Can be OpenAI, Anthropic,
                      Google, or OpenRouter.
                    </p>
                  </div>

                  <div className="form-group">
                    <label htmlFor="llmBaseUrl">API Base URL (optional)</label>
                    <input
                      id="llmBaseUrl"
                      type="url"
                      value={llmBaseUrl}
                      onChange={(e) => setLlmBaseUrl(e.target.value)}
                      placeholder="https://openrouter.ai/api/v1 (leave empty for default)"
                    />
                    <p className="form-help">
                      Custom endpoint. Leave empty for OpenRouter default.
                    </p>
                  </div>
                </>
              )}
              </div>
            </details>
          )}

          {/* Webhook Notifications */}
          <details className="settings-section quiet-disclosure">
            <summary>Webhook notifications</summary>
            <div className="settings-form">
              <div className="form-group">
                <label htmlFor="webhookUrl">Webhook URL</label>
                <input
                  id="webhookUrl"
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                />
                <p className="form-help">
                  Receive meeting updates. Leave empty to disable.
                </p>
              </div>
            </div>
          </details>

          {/* Account Management — local auth only */}
          {IS_COMMUNITY && (
            <details className="settings-section quiet-disclosure">
              <summary>Account</summary>

              {/* Change Password */}
              <div className="settings-form" style={{ marginBottom: "16px" }}>
                <p
                  className="settings-section-desc"
                  style={{ margin: "0 0 8px 0" }}
                >
                  Change Password
                </p>
                <div className="form-group">
                  <label htmlFor="currentPassword">Current Password</label>
                  <input
                    id="currentPassword"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Enter current password"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="newPassword">New Password</label>
                  <input
                    id="newPassword"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="At least 6 characters"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="confirmNewPassword">
                    Confirm New Password
                  </label>
                  <input
                    id="confirmNewPassword"
                    type="password"
                    value={confirmNewPassword}
                    onChange={(e) => setConfirmNewPassword(e.target.value)}
                    placeholder="Re-enter new password"
                  />
                </div>
                <div>
                  <button
                    className="btn-primary"
                    onClick={handleChangePassword}
                    disabled={passwordSaving}
                    style={{ width: "auto" }}
                  >
                    {passwordSaving ? "Changing..." : "Change Password"}
                  </button>
                </div>
              </div>

              {/* Delete Account */}
              <div className="settings-form">
                <p
                  className="settings-section-desc"
                  style={{ margin: "0 0 8px 0", color: "var(--ui-text)" }}
                >
                  Delete account
                </p>
                {!showDeleteConfirm ? (
                  <div>
                    <button
                      className="btn-danger"
                      onClick={() => setShowDeleteConfirm(true)}
                    >
                      Delete Account
                    </button>
                    <p className="form-help">
                      Permanently delete your account and all meeting data.
                    </p>
                  </div>
                ) : (
                  <div className="delete-confirm-box">
                    <p
                      style={{
                        fontSize: "13px",
                        color: "var(--ui-text)",
                        fontWeight: 600,
                        margin: "0 0 8px 0",
                      }}
                    >
                      This action is irreversible. All your meetings and data
                      will be permanently deleted.
                    </p>
                    <div className="form-group">
                      <label htmlFor="deletePassword">
                        Enter your password to confirm
                      </label>
                      <input
                        id="deletePassword"
                        type="password"
                        value={deletePassword}
                        onChange={(e) => setDeletePassword(e.target.value)}
                        placeholder="Your password"
                      />
                    </div>
                    <div
                      style={{ display: "flex", gap: "8px", marginTop: "8px" }}
                    >
                      <button
                        className="btn-danger"
                        onClick={handleDeleteAccount}
                        disabled={deleteLoading}
                      >
                        {deleteLoading ? "Deleting..." : "Confirm Delete"}
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => {
                          setShowDeleteConfirm(false);
                          setDeletePassword("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </details>
          )}

          {/* Messages */}
          {successMessage && (
            <div className="settings-message success" role="status">{successMessage}</div>
          )}

          {errorMessage && (
            <div className="settings-message error" role="alert">{errorMessage}</div>
          )}
        </div>

        {/* Footer actions - outside scrollable body */}
        <div className="settings-actions">
          <button
            className="btn-secondary"
            onClick={handleReset}
            disabled={isLoading}
          >
            Reset
          </button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={isLoading}
          >
            {isLoading ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}

export default Settings;
