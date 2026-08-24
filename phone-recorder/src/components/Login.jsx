import React, { useEffect, useState } from "react";
import "./Login.css";
import { IS_CLOUD } from "../config/edition";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
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
  const [isManorLoading, setIsManorLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    try {
      const manorError = localStorage.getItem("manor_login_error");
      const googleError = localStorage.getItem("google_login_error");
      const authError = manorError || googleError;
      if (authError) setError(authError);
      localStorage.removeItem("manor_login_error");
      localStorage.removeItem("google_login_error");
    } catch (_) {}
  }, []);

  const authBusy = isLoading || isGoogleLoading || isManorLoading;

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

  const handleManorLogin = async () => {
    setError("");
    try {
      localStorage.removeItem("manor_login_error");
    } catch (_) {}
    setIsManorLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/oauth/manor/start`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      const result = await response.json().catch(() => ({}));

      if (!response.ok || !result.authorize_url || !result.state) {
        throw new Error(
          result.detail || result.message || "Manor sign-in is not configured.",
        );
      }

      sessionStorage.setItem("manor_oauth_state", result.state);
      window.location.href = result.authorize_url;
    } catch (error) {
      console.error("Manor login error:", error);
      setError(error.message || "Manor sign-in failed. Please try again.");
      setIsManorLoading(false);
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
        setError("Google login is not configured. Please contact administrator.");
        setIsGoogleLoading(false);
        return;
      }

      const redirectUri =
        GOOGLE_REDIRECT_URI ||
        window.location.origin + window.location.pathname;
      const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?${new URLSearchParams(
        {
          client_id: GOOGLE_CLIENT_ID,
          redirect_uri: redirectUri,
          response_type: "code",
          scope: "openid email profile",
          include_granted_scopes: "true",
          access_type: "online",
        },
      ).toString()}`;

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
            disabled={authBusy}
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
              className="btn-manor-login"
              onClick={handleManorLogin}
              disabled={authBusy}
            >
              {isManorLoading ? (
                "Connecting to Manor..."
              ) : (
                <>
                  <img src="/manor.svg" alt="" className="manor-login-logo" />
                  Sign in with Manor
                </>
              )}
            </button>

            {GOOGLE_CLIENT_ID && (
              <button
                type="button"
                className="btn-google-login"
                onClick={handleGoogleLogin}
                disabled={authBusy}
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
            )}
          </>
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
