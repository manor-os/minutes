import React, { useState, useRef, useEffect } from "react";
import Recorder from "./components/Recorder";
import MeetingList from "./components/MeetingList";
import Login from "./components/Login";
import UserProfile from "./components/UserProfile";
import Notification from "./components/Notification";
import SharedMeeting from "./components/SharedMeeting";
import ManorCallback from "./components/ManorCallback";
import {
  MoonIcon,
  SunIcon,
  MonitorDesktopIcon,
  MicIcon,
} from "./components/Icons";
import { IS_CLOUD } from "./config/edition";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002"; // Backend API URL
const GOOGLE_REDIRECT_URI =
  import.meta.env.VITE_GOOGLE_REDIRECT_URI ||
  (typeof window !== "undefined"
    ? `${window.location.origin}/googleCallback`
    : "");

// Suppress Chrome extension "message port closed" errors
// This is a harmless error that occurs when the extension's background service worker is inactive
if (typeof window !== "undefined") {
  const originalError = console.error;
  console.error = function (...args) {
    const message = args.join(" ");
    // Suppress the specific Chrome extension error
    if (
      message.includes("runtime.lastError") &&
      message.includes("message port closed")
    ) {
      // Silently ignore - this is expected behavior when extension service worker is inactive
      return;
    }
    originalError.apply(console, args);
  };
}

function AppRouter() {
  if (window.location.pathname === "/auth/manor-callback") {
    return <ManorCallback />;
  }

  // Check for shared meeting URL — render standalone view with no auth
  const sharedMatch = window.location.pathname.match(/^\/shared\/([a-f0-9]+)$/);
  if (sharedMatch) {
    return <SharedMeeting shareToken={sharedMatch[1]} />;
  }
  return <App />;
}

function App() {
  const [recordings, setRecordings] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [currentRecording, setCurrentRecording] = useState(null);
  const [view, setView] = useState("recorder"); // 'recorder' or 'list'
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [notification, setNotification] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [showSettings, setShowSettings] = useState(false);
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "system",
  );
  const urlMeetingHandled = useRef(false);
  const prevProcessingIds = useRef(new Set());

  // Apply dark mode theme
  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    localStorage.setItem("theme", theme);
  }, [theme]);

  const cycleTheme = () => {
    setTheme((prev) => {
      if (prev === "system") return "dark";
      if (prev === "dark") return "light";
      return "system";
    });
  };

  // Request browser notification permission on mount
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Check authentication on mount
  useEffect(() => {
    try {
      let hash = "";
      let pathname = "";
      let search = "";

      try {
        hash = window.location.hash || "";
        pathname = window.location.pathname || "";
        search = window.location.search || "";
      } catch (locationError) {
        console.warn(
          "Error accessing window.location, using defaults:",
          locationError,
        );
        hash = "";
        pathname = "/";
        search = "";
      }

      if (window.__GOOGLE_CALLBACK_BOOTSTRAPPED__) {
        setIsCheckingAuth(true);
        return;
      }

      if (IS_CLOUD && (hash.includes("access_token=") || pathname.includes("googleCallback"))) {
        let params = new URLSearchParams();
        try {
          params = pathname.includes("googleCallback")
            ? new URLSearchParams(search)
            : new URLSearchParams(hash.substring(1));
        } catch (parseError) {
          console.error("Error parsing Google callback:", parseError);
          localStorage.setItem("google_login_error", "Invalid Google sign-in callback.");
          try {
            window.history.replaceState({}, "", "/");
          } catch (_) {}
          setIsCheckingAuth(false);
          return;
        }

        const errorParam = params.get("error");
        if (errorParam) {
          localStorage.setItem("google_login_error", `Google sign-in cancelled: ${errorParam}`);
          try {
            window.history.replaceState({}, "", "/");
          } catch (_) {}
          setIsCheckingAuth(false);
          return;
        }

        const code = params.get("code");
        const accessToken = params.get("access_token");
        try {
          window.history.replaceState({}, "", "/");
        } catch (e) {
          console.warn("Error cleaning up Google callback URL:", e);
        }
        if (code || accessToken) {
          handleGoogleCallback(params);
          return;
        }
      }

      if (hash.includes("access_token=") || pathname.includes("googleCallback")) {
        try {
          window.history.replaceState({}, "", "/");
        } catch (e) {
          console.warn("Error cleaning up legacy OAuth URL:", e);
        }
      }

      checkAuthentication();
    } catch (error) {
      console.error("Error in authentication check:", error);
      checkAuthentication();
    }
  }, []);

  const handleGoogleCallback = async (params) => {
    const recordFailure = (detail) => {
      const msg = detail || "Google sign-in failed. Please try again.";
      console.error("Google callback failed:", msg);
      try {
        localStorage.setItem("google_login_error", msg);
      } catch (_) {}
      try {
        window.history.replaceState({}, "", "/");
      } catch (_) {}
    };

    try {
      const code = params.get("code");
      if (!code) {
        recordFailure("Google sign-in returned no authorization code.");
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/auth/google-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          redirect_uri: GOOGLE_REDIRECT_URI || `${window.location.origin}/googleCallback`,
          state: params.get("state") || "",
        }),
      });
      const result = await response.json().catch(() => ({}));

      if (!response.ok || !result.success || !result.token) {
        recordFailure(result.detail || result.message || "Google sign-in failed.");
        return;
      }

      try {
        localStorage.removeItem("google_login_error");
      } catch (_) {}

      localStorage.setItem("auth_token", result.token);
      localStorage.setItem("entity_id", result.entity_id || "");
      localStorage.setItem("user_email", result.email || "");
      localStorage.setItem("user_name", result.name || "");

      setUser({
        token: result.token,
        entity_id: result.entity_id,
        email: result.email,
        name: result.name,
      });
      setIsAuthenticated(true);
    } catch (error) {
      recordFailure(error.message || String(error));
    } finally {
      setIsCheckingAuth(false);
    }
  };

  // Check for meeting ID in URL params on mount only
  useEffect(() => {
    if (isAuthenticated && !urlMeetingHandled.current) {
      try {
        // Check if there's a meeting ID in URL params (only on initial load)
        // Safely access window.location.search
        let search = "";
        try {
          search = window.location.search || "";
        } catch (locationError) {
          console.warn(
            "Error accessing window.location.search:",
            locationError,
          );
          urlMeetingHandled.current = true;
          return;
        }

        let urlParams;
        try {
          urlParams = new URLSearchParams(search);
        } catch (parseError) {
          console.warn("Error parsing URL search params:", parseError);
          urlMeetingHandled.current = true;
          return;
        }

        const meetingId = urlParams.get("meeting");
        if (meetingId) {
          urlMeetingHandled.current = true;
          // Switch to list view and scroll to the meeting
          setView("list");
          setTimeout(() => {
            const meetingElement = document.querySelector(
              `[data-meeting-id="${meetingId}"]`,
            );
            if (meetingElement) {
              meetingElement.scrollIntoView({
                behavior: "smooth",
                block: "center",
              });
              meetingElement.style.border = "2px solid #2196F3";
              meetingElement.style.boxShadow =
                "0 0 10px rgba(33, 150, 243, 0.3)";
              setTimeout(() => {
                meetingElement.style.border = "";
                meetingElement.style.boxShadow = "";
              }, 3000);
            }
          }, 500);
          // Clean up URL param after handling
          try {
            let pathname = "/";
            try {
              pathname = window.location.pathname || "/";
            } catch (pathError) {
              console.warn(
                "Error accessing window.location.pathname:",
                pathError,
              );
              pathname = "/";
            }
            window.history.replaceState({}, "", pathname);
          } catch (e) {
            console.warn("Error cleaning up URL:", e);
          }
        } else {
          urlMeetingHandled.current = true;
        }
      } catch (error) {
        console.error("Error in URL meeting check:", error);
        urlMeetingHandled.current = true;
      }
    }
  }, [isAuthenticated]); // Only run when authentication changes

  // Load recordings when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadRecordings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]); // Only run when authentication changes

  // Reset to page 1 when search/sort/filter changes
  // The page change will trigger its own reload via the effect below
  const searchSortFilterRef = useRef({ searchQuery, sortBy, statusFilter });
  useEffect(() => {
    if (!isAuthenticated) return;
    const prev = searchSortFilterRef.current;
    searchSortFilterRef.current = { searchQuery, sortBy, statusFilter };
    // If filters changed, reset to page 1 (which triggers the page effect)
    // If page is already 1, the page effect won't re-fire, so load explicitly
    if (
      prev.searchQuery !== searchQuery ||
      prev.sortBy !== sortBy ||
      prev.statusFilter !== statusFilter
    ) {
      if (page === 1) {
        loadRecordings(1);
      } else {
        setPage(1);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, sortBy, statusFilter]);

  // Reload when page changes
  useEffect(() => {
    if (isAuthenticated) {
      loadRecordings(page);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // Auto-refresh based on user preferences (only when on list view)
  useEffect(() => {
    if (!isAuthenticated || view !== "list") {
      return;
    }

    const autoRefreshEnabled =
      localStorage.getItem("auto_refresh_enabled") !== "false";
    const refreshInterval =
      parseInt(localStorage.getItem("refresh_interval") || "5", 10) * 1000;

    let interval = null;
    if (autoRefreshEnabled) {
      interval = setInterval(() => {
        loadRecordings();
      }, refreshInterval);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [isAuthenticated, view]); // Run when view changes, but only refresh if on list view

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't trigger if user is typing in an input/textarea
      if (
        e.target.tagName === "INPUT" ||
        e.target.tagName === "TEXTAREA" ||
        e.target.tagName === "SELECT"
      )
        return;

      // Don't trigger if modifier keys (except for combinations)
      if (e.metaKey || e.ctrlKey) {
        // Cmd/Ctrl+K — focus search (if on list view)
        if (e.key === "k") {
          e.preventDefault();
          setView("list");
          setTimeout(() => {
            const searchInput = document.querySelector(".search-input");
            if (searchInput) searchInput.focus();
          }, 100);
        }
        return;
      }

      if (e.altKey) return;

      switch (e.key) {
        case "r":
          // R — start recording (only if not already recording and on recorder view)
          if (!isRecording && view === "recorder") {
            // Trigger start recording
            document.querySelector(".btn-start")?.click();
          }
          break;
        case "s":
          // S — stop recording
          if (isRecording) {
            document.querySelector(".btn-stop")?.click();
          }
          break;
        case "1":
          setView("recorder");
          break;
        case "2":
          setView("list");
          break;
        case "?":
          // Show keyboard shortcuts help
          setNotification({
            message:
              "Shortcuts: 1=Recorder, 2=Meetings, R=Record, S=Stop, Cmd+K=Search, D=Dark mode",
            type: "info",
          });
          break;
        case "d":
          // D — toggle dark mode
          document.querySelector(".theme-toggle-btn")?.click();
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRecording, view]);

  const checkAuthentication = async () => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      setIsAuthenticated(false);
      setIsCheckingAuth(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        // Token invalid or expired - clear it silently
        localStorage.removeItem("auth_token");
        localStorage.removeItem("entity_id");
        localStorage.removeItem("user_email");
        localStorage.removeItem("user_name");
        setIsAuthenticated(false);
        setIsCheckingAuth(false);
        return;
      }

      const result = await response.json();
      if (result.success && result.valid) {
        setIsAuthenticated(true);
        setUser({
          entity_id: result.entity_id,
          email: result.email,
          name: result.name,
          user_id: result.user_id,
        });
      } else {
        // Token invalid, clear it
        localStorage.removeItem("auth_token");
        localStorage.removeItem("entity_id");
        localStorage.removeItem("user_email");
        localStorage.removeItem("user_name");
        setIsAuthenticated(false);
      }
    } catch (error) {
      // Network error - check if backend is reachable
      console.warn(
        "Auth check failed (this is normal if not logged in):",
        error.message,
      );
      // Clear token if it exists (might be invalid)
      localStorage.removeItem("auth_token");
      localStorage.removeItem("entity_id");
      localStorage.removeItem("user_email");
      localStorage.removeItem("user_name");
      setIsAuthenticated(false);
    } finally {
      setIsCheckingAuth(false);
    }
  };

  const handleLoginSuccess = (userData) => {
    setIsAuthenticated(true);
    setUser(userData);
    // Token will be synced to chrome.storage by the extension's auth-sync.js content script
  };

  const handleLogout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("entity_id");
    localStorage.removeItem("user_email");
    localStorage.removeItem("user_name");
    setIsAuthenticated(false);
    setUser(null);
  };

  const getAuthHeaders = () => {
    const token = localStorage.getItem("auth_token");
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  };

  const loadRecordings = async (pageOverride) => {
    try {
      const currentPage = pageOverride || page;
      const params = new URLSearchParams();
      params.set("page", String(currentPage));
      params.set("per_page", "20");
      if (searchQuery) params.set("q", searchQuery);
      if (sortBy) params.set("sort", sortBy);
      if (statusFilter === "favorites") {
        params.set("favorite", "true");
      } else if (statusFilter) {
        params.set("status", statusFilter);
      }
      const queryString = params.toString();
      const url = `${API_BASE_URL}/api/meetings/list${queryString ? "?" + queryString : ""}`;
      const response = await fetch(url, {
        headers: getAuthHeaders(),
      });

      if (response.status === 401) {
        // Token expired or invalid
        handleLogout();
        return;
      }

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`HTTP error! status: ${response.status}`, errorText);
        // Don't show alert for 401 - it's handled above
        if (response.status !== 401) {
          console.error("Failed to load meetings:", errorText);
        }
        return;
      }
      const data = await response.json();
      if (data.success) {
        const meetings = data.meetings || [];

        // Update pagination state
        if (data.total_pages !== undefined) {
          setTotalPages(data.total_pages);
        }

        // Check for newly completed meetings (was processing, now completed)
        const currentProcessing = new Set(
          meetings
            .filter(
              (m) => m.status === "processing" || m.status === "uploading",
            )
            .map((m) => m.id),
        );
        const newlyCompleted = meetings.filter(
          (m) =>
            m.status === "completed" && prevProcessingIds.current.has(m.id),
        );

        newlyCompleted.forEach((meeting) => {
          // Browser notification
          if (
            "Notification" in window &&
            Notification.permission === "granted"
          ) {
            new Notification("Meeting Ready", {
              body: `"${meeting.title || "Untitled"}" has been transcribed and summarized.`,
              icon: "/favicon.svg",
            });
          }
          // In-app notification
          setNotification({
            message: `"${meeting.title || "Untitled"}" is ready!`,
            type: "success",
          });
        });

        prevProcessingIds.current = currentProcessing;

        setRecordings(meetings);
      } else {
        console.error("API returned error:", data);
      }
    } catch (error) {
      console.error("Error loading recordings:", error);
      // Silent error - don't show alert, just log it
    }
  };

  const handleRecordingComplete = async (audioBlob, metadata) => {
    try {
      const formData = new FormData();
      formData.append("audio", audioBlob, "phone_recording.webm");
      const transcriptLanguage =
        localStorage.getItem("transcript_language") || "";
      formData.append(
        "metadata",
        JSON.stringify({
          ...metadata,
          source: "phone_recorder",
          language: transcriptLanguage || undefined,
        }),
      );

      // Upload asynchronously - don't wait for response
      const token = localStorage.getItem("auth_token");
      const headers = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      // Don't set Content-Type header - browser will set it with boundary for FormData
      fetch(`${API_BASE_URL}/api/meetings/upload`, {
        method: "POST",
        headers: headers,
        body: formData,
      })
        .then(async (response) => {
          if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `Upload failed: ${response.status} ${response.statusText}`;
            try {
              const errorJson = JSON.parse(errorText);
              errorMessage = `Upload failed: ${response.status} ${response.statusText} - ${JSON.stringify(errorJson)}`;
            } catch {
              errorMessage = `Upload failed: ${response.status} ${response.statusText} - ${errorText}`;
            }
            console.error("❌ Upload error:", errorMessage);

            // Show error notification
            setNotification({
              message: "Recording upload failed. Please try again.",
              type: "error",
            });

            if (response.status === 401) {
              // Token expired or invalid - logout user
              handleLogout();
            }
            return;
          }

          const result = await response.json();
          if (result.success) {
            const meetingId = result.meeting_id || result.id;
            const meetingTitle = metadata.title || "Recording";

            // Reload recordings to show the new meeting
            await loadRecordings();

            // Show success notification with link to meeting
            setNotification({
              message: `Recording "${meetingTitle}" uploaded successfully!`,
              type: "success",
              meetingId: meetingId,
              onAction: () => navigateToMeeting(meetingId),
            });
          } else {
            console.error("Upload failed:", result.error || "Unknown error");
            setNotification({
              message: result.error || "Upload failed. Please try again.",
              type: "error",
            });
          }
        })
        .catch((error) => {
          console.error("Error uploading recording:", error);
          setNotification({
            message: "Error uploading recording. Please check your connection.",
            type: "error",
          });
        });

      // Reload recordings in background to update the list
      loadRecordings();
    } catch (error) {
      console.error("Error preparing upload:", error);
      setNotification({
        message: "Error preparing recording. Please try again.",
        type: "error",
      });
    }
  };

  const navigateToMeeting = (meetingId) => {
    if (!meetingId) return;

    // Close notification
    setNotification(null);

    // Convert meetingId to string for consistent comparison
    const meetingIdStr = String(meetingId);

    // Switch to list view
    setView("list");

    // Wait for view to update, then scroll to meeting
    setTimeout(() => {
      const meetingElement = document.querySelector(
        `[data-meeting-id="${meetingIdStr}"]`,
      );
      if (meetingElement) {
        meetingElement.scrollIntoView({ behavior: "smooth", block: "center" });
        // Highlight the meeting
        meetingElement.style.border = "2px solid #2196F3";
        meetingElement.style.boxShadow = "0 0 10px rgba(33, 150, 243, 0.3)";
        setTimeout(() => {
          meetingElement.style.border = "";
          meetingElement.style.boxShadow = "";
        }, 3000);
      } else {
        // If element not found, refresh recordings and try again
        loadRecordings().then(() => {
          setTimeout(() => {
            const retryElement = document.querySelector(
              `[data-meeting-id="${meetingIdStr}"]`,
            );
            if (retryElement) {
              retryElement.scrollIntoView({
                behavior: "smooth",
                block: "center",
              });
              retryElement.style.border = "2px solid #2196F3";
              retryElement.style.boxShadow = "0 0 10px rgba(33, 150, 243, 0.3)";
              setTimeout(() => {
                retryElement.style.border = "";
                retryElement.style.boxShadow = "";
              }, 3000);
            }
          }, 500);
        });
      }
    }, 300);
  };

  // Show loading state while checking authentication
  if (isCheckingAuth) {
    return (
      <div className="app">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Checking authentication...</p>
        </div>
      </div>
    );
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  // Show main app if authenticated
  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1>
            <img src="/logo.svg" alt="Minutes" className="app-logo" />
          </h1>
        </div>
        <div className="header-right">
          <nav className="nav-tabs">
            <button
              className={view === "recorder" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                urlMeetingHandled.current = true;
                setView("recorder");
              }}
            >
              Recorder
            </button>
            <button
              className={view === "list" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setView("list");
              }}
            >
              My Meetings
            </button>
          </nav>
          <button
            className="theme-toggle-btn"
            onClick={cycleTheme}
            title={
              theme === "system"
                ? "Theme: Auto (system) — click for dark"
                : theme === "dark"
                  ? "Theme: Dark — click for light"
                  : "Theme: Light — click for auto"
            }
          >
            {theme === "dark" ? (
              <MoonIcon size={16} />
            ) : theme === "light" ? (
              <SunIcon size={16} />
            ) : (
              <MonitorDesktopIcon size={16} />
            )}
          </button>
          <UserProfile
            user={user}
            onLogout={handleLogout}
            showSettings={showSettings}
            onSettingsClose={() => setShowSettings(false)}
            onUserUpdate={(updatedUser) => {
              setUser(updatedUser);
              // Update localStorage
              if (updatedUser.name) {
                localStorage.setItem("user_name", updatedUser.name);
              }
              if (updatedUser.email) {
                localStorage.setItem("user_email", updatedUser.email);
              }
            }}
          />
        </div>
      </header>

      <main className="app-main">
        {/* Keep Recorder mounted during recording to preserve media streams */}
        <div
          style={{
            display: view === "recorder" || isRecording ? "contents" : "none",
          }}
        >
          <Recorder
            onRecordingComplete={handleRecordingComplete}
            isRecording={isRecording}
            setIsRecording={setIsRecording}
            onNotification={setNotification}
            hidden={view !== "recorder"}
            onOpenSettings={() => setShowSettings(true)}
          />
        </div>
        {view === "list" && (
          <MeetingList
            recordings={recordings}
            onRefresh={loadRecordings}
            onNotification={setNotification}
            currentUser={user}
            searchQuery={searchQuery}
            sortBy={sortBy}
            statusFilter={statusFilter}
            onSearchChange={setSearchQuery}
            onSortChange={setSortBy}
            onStatusChange={setStatusFilter}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
          />
        )}
        {/* Live transcription is now built into the Recorder */}
      </main>

      <footer className="app-footer">
        <p className="powered-by">
          Powered by <span className="manor-ai-brand">Manor AI</span>
        </p>
      </footer>

      {/* Notification */}
      {notification && (
        <Notification
          message={notification.message}
          type={notification.type}
          onClose={() => setNotification(null)}
          onAction={notification.onAction}
          actionLabel="View Meeting"
        />
      )}
    </div>
  );
}

export default AppRouter;
