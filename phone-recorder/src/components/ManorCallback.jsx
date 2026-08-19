import React, { useEffect, useRef, useState } from "react";
import { IS_CLOUD } from "../config/edition";
import "./Login.css";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";

function persistLoginResult(result) {
  localStorage.setItem("auth_token", result.token);
  localStorage.setItem("entity_id", result.entity_id || "");
  localStorage.setItem("user_email", result.email || "");
  localStorage.setItem("user_name", result.name || "");
}

function redirectHome() {
  window.location.replace("/");
}

function consumeExpectedState() {
  try {
    const state = sessionStorage.getItem("manor_oauth_state");
    sessionStorage.removeItem("manor_oauth_state");
    return state;
  } catch (_) {
    return null;
  }
}

function ManorCallback() {
  const [status, setStatus] = useState("Completing Manor sign-in...");
  const [error, setError] = useState("");
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    if (window.__MANOR_CALLBACK_BOOTSTRAPPED__) {
      setStatus("Completing Manor sign-in...");
      return;
    }

    const fail = (message) => {
      const detail = message || "Manor sign-in failed. Please try again.";
      console.error("Manor callback failed:", detail);
      setError(detail);
      setStatus("Redirecting to sign in...");
      try {
        localStorage.setItem("manor_login_error", detail);
      } catch (_) {}
      window.setTimeout(redirectHome, 1200);
    };

    const complete = async () => {
      if (!IS_CLOUD) {
        fail("Manor sign-in is only available in cloud edition.");
        return;
      }

      const params = new URLSearchParams(window.location.search || "");
      const code = params.get("code");
      const state = params.get("state");
      const errorParam = params.get("error");
      const savedState = consumeExpectedState();

      if (errorParam) {
        fail(`Manor sign-in cancelled: ${errorParam}`);
        return;
      }
      if (!code || !state) {
        fail("Manor sign-in returned no authorization code.");
        return;
      }
      if (savedState && savedState !== state) {
        fail("Sign-in state mismatch. Please try again.");
        return;
      }

      setStatus("Exchanging Manor authorization code...");
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 35000);

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/auth/oauth/manor/callback`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code, state }),
            signal: controller.signal,
          },
        );
        const result = await response.json().catch(() => ({}));

        if (!response.ok || !result.success || !result.token) {
          fail(result.detail || result.message || "Manor sign-in failed.");
          return;
        }

        try {
          localStorage.removeItem("manor_login_error");
        } catch (_) {}

        persistLoginResult(result);
        setStatus("Signed in. Redirecting...");
        redirectHome();
      } catch (callbackError) {
        if (callbackError.name === "AbortError") {
          fail("Manor sign-in timed out. Please try again.");
        } else {
          fail(callbackError.message || String(callbackError));
        }
      } finally {
        window.clearTimeout(timeoutId);
      }
    };

    complete();
  }, []);

  return (
    <div className="login-container">
      <div className="login-card callback-card">
        <div className="login-header">
          <img src="/logo.svg" alt="Minutes" className="login-logo" />
          <h1 className="callback-title">Signing in with Manor</h1>
          <p className="login-subtitle">{status}</p>
        </div>

        {!error && <div className="callback-spinner" aria-label="Loading" />}
        {error && <div className="error-message">{error}</div>}

        {error && (
          <div className="callback-actions">
            <button type="button" className="btn-login" onClick={redirectHome}>
              Back to sign in
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ManorCallback;
