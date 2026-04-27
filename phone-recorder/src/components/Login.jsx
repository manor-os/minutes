import React, { useState } from "react";
import { MicIcon } from "./Icons";
import "./Login.css";
import { IS_CLOUD, IS_COMMUNITY } from "../config/edition";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";
const DEFAULT_ADMIN_EMAIL = import.meta.env.VITE_DEFAULT_ADMIN_EMAIL || "admin@minutes.local";
const DEFAULT_ADMIN_PASSWORD = import.meta.env.VITE_DEFAULT_ADMIN_PASSWORD || "admin";
const GOOGLE_CLIENT_ID =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  "991498874043-94og2o7k4pnrl9q3s3si2mvhdcovaqic.apps.googleusercontent.com";
// Default to the current site's /googleCallback so each deployment returns to itself.
// Override with VITE_GOOGLE_REDIRECT_URI if you need a fixed callback.
const GOOGLE_REDIRECT_URI =
  import.meta.env.VITE_GOOGLE_REDIRECT_URI ||
  (typeof window !== "undefined"
    ? `${window.location.origin}/googleCallback`
    : "");

function Login({ onLoginSuccess }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  // Surface any prior Google-login failure recorded by App.jsx so the user
  // (and we) can see exactly what went wrong instead of silently bouncing
  // back to a blank login form.
  const [error, setError] = useState(() => {
    try {
      const stored = localStorage.getItem("google_login_error");
      if (stored) {
        return `Google login failed: ${stored}`;
      }
    } catch (_) {}
    return "";
  });

  const fillDefaultCredentials = () => {
    setEmail(DEFAULT_ADMIN_EMAIL);
    setPassword(DEFAULT_ADMIN_PASSWORD);
    setIsRegister(false);
    setError("");
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      if (!email || !email.includes("@")) {
        setError("Please enter a valid email address");
        setIsLoading(false);
        return;
      }

      if (!password) {
        setError("Please enter your password");
        setIsLoading(false);
        return;
      }

      const loginData = {
        email: email,
        password: password,
      };

      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(loginData),
      });

      const result = await response.json();

      if (result.success && result.token) {
        // Store token in localStorage
        localStorage.setItem("auth_token", result.token);
        localStorage.setItem("entity_id", result.entity_id);
        localStorage.setItem("user_email", result.email || "");
        localStorage.setItem("user_name", result.name || "");

        // Token will be synced to chrome.storage by the extension's auth-sync.js content script

        // Notify parent component
        if (onLoginSuccess) {
          onLoginSuccess({
            token: result.token,
            entity_id: result.entity_id,
            email: result.email,
            name: result.name,
          });
        }
      } else {
        setError(
          result.message || "Login failed. Please check your credentials.",
        );
      }
    } catch (error) {
      console.error("Login error:", error);
      setError("Login failed. Please check your connection and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      if (!email || !email.includes("@")) {
        setError("Please enter a valid email address");
        setIsLoading(false);
        return;
      }
      if (!password || password.length < 6) {
        setError("Password must be at least 6 characters");
        setIsLoading(false);
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name: name || undefined }),
      });

      const result = await response.json();

      if (response.status === 409) {
        setError("Email already registered. Please login instead.");
        setIsLoading(false);
        return;
      }

      if (result.success && result.token) {
        localStorage.setItem("auth_token", result.token);
        localStorage.setItem("entity_id", result.entity_id || "");
        localStorage.setItem("user_email", result.email || "");
        localStorage.setItem("user_name", result.name || "");

        if (onLoginSuccess) {
          onLoginSuccess({
            token: result.token,
            entity_id: result.entity_id,
            email: result.email,
            name: result.name,
          });
        }
      } else {
        setError(result.detail || result.message || "Registration failed.");
      }
    } catch (error) {
      console.error("Register error:", error);
      setError("Registration failed. Please check your connection.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError("");
    try {
      localStorage.removeItem("google_login_error");
    } catch (_) {}
    setIsGoogleLoading(true);

    try {
      if (!GOOGLE_CLIENT_ID) {
        setError(
          "Google login is not configured. Please contact administrator.",
        );
        setIsGoogleLoading(false);
        return;
      }

      // Use Google OAuth 2.0 redirect flow
      const redirectUri =
        GOOGLE_REDIRECT_URI ||
        window.location.origin + window.location.pathname;
      const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?${new URLSearchParams(
        {
          client_id: GOOGLE_CLIENT_ID,
          redirect_uri: redirectUri,
          response_type: "token",
          scope: "openid email profile",
          include_granted_scopes: "true",
        },
      ).toString()}`;

      // Redirect to Google OAuth (full page redirect)
      // The callback will be handled by App.jsx when Google redirects back
      window.location.href = googleAuthUrl;
    } catch (error) {
      console.error("Google login error:", error);
      setError("Google login failed. Please try again.");
      setIsGoogleLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <img src="/logo.svg" alt="Minutes" className="login-logo" />
          <p className="login-subtitle">
            {isRegister ? "Create your account" : "Sign in to continue"}
          </p>
        </div>

        <form
          onSubmit={isRegister ? handleRegister : handleLogin}
          className="login-form"
        >
          {isRegister && (
            <div className="form-group">
              <label htmlFor="name">Name (optional)</label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                disabled={isLoading}
              />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              required
              disabled={isLoading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={
                isRegister
                  ? "Create a password (min 6 chars)"
                  : "Enter your password"
              }
              required
              disabled={isLoading}
            />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button
            type="submit"
            className="btn-login"
            disabled={isLoading || isGoogleLoading}
          >
            {isLoading
              ? isRegister
                ? "Creating account..."
                : "Logging in..."
              : isRegister
                ? "Create Account"
                : "Login"}
          </button>
        </form>

        <div className="login-toggle">
          <span>
            {isRegister ? "Already have an account?" : "Don't have an account?"}
          </span>
          <button
            type="button"
            className="btn-toggle-mode"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
            }}
          >
            {isRegister ? "Sign in" : "Register"}
          </button>
        </div>

        {IS_CLOUD && (
          <>
            <div className="login-divider">
              <span>or</span>
            </div>

            <button
              type="button"
              className="btn-google-login"
              onClick={handleGoogleLogin}
              disabled={isLoading || isGoogleLoading}
            >
              {isGoogleLoading ? (
                "Connecting to Google..."
              ) : (
                <>
                  <svg
                    className="google-icon"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                  >
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  Continue with Google
                </>
              )}
            </button>
          </>
        )}

        {IS_COMMUNITY && !isRegister && (
          <div className="default-credentials">
            <div className="default-credentials-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              <span>Default admin account</span>
            </div>
            <div className="default-credentials-body">
              <div className="credential-row">
                <span className="credential-label">Email</span>
                <code className="credential-value">{DEFAULT_ADMIN_EMAIL}</code>
              </div>
              <div className="credential-row">
                <span className="credential-label">Password</span>
                <code className="credential-value">{DEFAULT_ADMIN_PASSWORD}</code>
              </div>
            </div>
            <button
              type="button"
              className="btn-fill-defaults"
              onClick={fillDefaultCredentials}
            >
              Quick fill
            </button>
          </div>
        )}

        <div className="login-footer">
          <p className="login-help">
            Free and open source. Bring your own API key.
          </p>
        </div>
      </div>
    </div>
  );
}

export default Login;
