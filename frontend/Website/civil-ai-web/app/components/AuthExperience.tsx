"use client";

import Image from "next/image";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { SiteHeader } from "./SiteHeader";
import { useAuth } from "../context/AuthContext";
import { CUSTOM_API_BASE } from "../lib/apiConfig";

type AuthMode = "login" | "register";

interface JurisdictionOption {
  name: string;
  chunks: number;
}

interface AuthExperienceProps {
  initialMode: AuthMode;
}

export function AuthExperience({ initialMode }: AuthExperienceProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [nextPath, setNextPath] = useState("/chat");
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");

  const { isAuthenticated, isLoading: isAuthLoading, login, register, continueAsGuest } =
    useAuth();
  const router = useRouter();

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const rawValue = new URLSearchParams(window.location.search).get("next");
    if (rawValue && rawValue.startsWith("/")) {
      setNextPath(rawValue);
    }
  }, []);

  useEffect(() => {
    if (!isAuthLoading && isAuthenticated) {
      router.replace(nextPath);
    }
  }, [isAuthenticated, isAuthLoading, nextPath, router]);

  useEffect(() => {
    let isMounted = true;

    async function loadJurisdictions() {
      try {
        const response = await fetch(`${CUSTOM_API_BASE}/jurisdictions`);
        if (!response.ok) {
          return;
        }

        const payload = (await response.json()) as {
          jurisdictions?: JurisdictionOption[];
        };

        if (isMounted) {
          setJurisdictions(payload.jurisdictions ?? []);
        }
      } catch {
        if (isMounted) {
          setJurisdictions([]);
        }
      }
    }

    void loadJurisdictions();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  async function handleLoginSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      await login(loginUsername, loginPassword);
      router.push(nextPath);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Login failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRegisterSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setIsLoading(true);

    try {
      await register({
        email,
        username,
        password,
        full_name: fullName || undefined,
        jurisdiction: jurisdiction || undefined,
      });
      router.push(nextPath);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Registration failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleGuestContinue() {
    setError("");
    setIsLoading(true);
    try {
      await continueAsGuest({
        full_name: fullName || "Guest User",
        jurisdiction: jurisdiction || undefined,
      });
      router.push(nextPath);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="app-shell auth-app-shell auth-shell">
      <div className="page-frame auth-page-frame auth-frame">
        <SiteHeader />

        <main className="auth-main">
          <div className="auth-canvas">
            <div className="auth-photo-layer">
              <Image
                src="/images/auth/login-drawing.jpg"
                alt="Drafting tools on an engineering plan."
                fill
                priority
                className="auth-photo"
                sizes="100vw"
              />
            </div>

            <div className={`auth-ribbon auth-ribbon-${mode}`}>
              <motion.div
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className="auth-ribbon-inner"
              >
                <div className="auth-prelude">
                  <span className="quiet-chip">Municipal code workspace</span>
                  <span className="quiet-chip">Guest access included</span>
                </div>

                <div className="auth-copy">
                  <p className="eyebrow">Start fast, keep what matters.</p>
                  <h1 className="auth-display">
                    {mode === "login" ? (
                      <>
                        Return to the <span className="heading-accent">code trail</span> you
                        already started.
                      </>
                    ) : (
                      <>
                        Create a <span className="heading-accent">workspace</span> for ordinance
                        answers you can reuse.
                      </>
                    )}
                  </h1>
                  <p className="panel-copy">
                    CivilAI helps engineers, planners, and reviewers move from scattered PDF
                    searching to cited answers. Sign in when the thread should persist, or continue
                    as a guest when you only need a quick test.
                  </p>
                </div>

                <div className="auth-ledger">
                  <span>Saved project questions</span>
                  <span>Default jurisdiction focus</span>
                  <span>Answers tied to sources</span>
                </div>

                <div className="auth-switch" role="tablist" aria-label="Authentication mode">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={mode === "login"}
                    className={mode === "login" ? "auth-switch-link auth-switch-link-active" : "auth-switch-link"}
                    onClick={() => {
                      setError("");
                      setMode("login");
                    }}
                  >
                    Sign in
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={mode === "register"}
                    className={mode === "register" ? "auth-switch-link auth-switch-link-active" : "auth-switch-link"}
                    onClick={() => {
                      setError("");
                      setMode("register");
                    }}
                  >
                    Create account
                  </button>
                </div>

                {error ? <div className="status-banner status-error">{error}</div> : null}

                <AnimatePresence mode="wait" initial={false}>
                  {mode === "login" ? (
                    <motion.form
                      key="login"
                      className="auth-form-flow"
                      onSubmit={handleLoginSubmit}
                      initial={{ opacity: 0, y: 24, filter: "blur(6px)" }}
                      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                      exit={{ opacity: 0, y: -20, filter: "blur(6px)" }}
                      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <div className="field">
                        <label className="field-label" htmlFor="loginUsername">
                          Username
                        </label>
                        <input
                          id="loginUsername"
                          className="field-input auth-field"
                          type="text"
                          value={loginUsername}
                          onChange={(event) => setLoginUsername(event.target.value)}
                          placeholder="Enter your username"
                          required
                          autoComplete="username"
                        />
                      </div>

                      <div className="field">
                        <label className="field-label" htmlFor="loginPassword">
                          Password
                        </label>
                        <input
                          id="loginPassword"
                          className="field-input auth-field"
                          type="password"
                          value={loginPassword}
                          onChange={(event) => setLoginPassword(event.target.value)}
                          placeholder="Enter your password"
                          required
                          autoComplete="current-password"
                        />
                      </div>

                      <div className="auth-action-row">
                        <button
                          type="submit"
                          className="button button-primary"
                          disabled={isLoading || !loginUsername || !loginPassword}
                        >
                          {isLoading ? "Signing in..." : "Sign in"}
                        </button>
                        <button
                          type="button"
                          className="button button-subtle"
                          onClick={() => void handleGuestContinue()}
                          disabled={isLoading}
                        >
                          Continue as guest
                        </button>
                      </div>
                    </motion.form>
                  ) : (
                    <motion.form
                      key="register"
                      className="auth-form-flow"
                      onSubmit={handleRegisterSubmit}
                      initial={{ opacity: 0, y: 24, filter: "blur(6px)" }}
                      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                      exit={{ opacity: 0, y: -20, filter: "blur(6px)" }}
                      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <div className="auth-field-grid">
                        <div className="field">
                          <label className="field-label" htmlFor="registerEmail">
                            Email
                          </label>
                          <input
                            id="registerEmail"
                            className="field-input auth-field"
                            type="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            placeholder="you@example.com"
                            required
                            autoComplete="email"
                          />
                        </div>

                        <div className="field">
                          <label className="field-label" htmlFor="registerUsername">
                            Username
                          </label>
                          <input
                            id="registerUsername"
                            className="field-input auth-field"
                            type="text"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                            placeholder="Choose a username"
                            required
                            autoComplete="username"
                            minLength={3}
                          />
                        </div>
                      </div>

                      <div className="auth-field-grid">
                        <div className="field">
                          <label className="field-label" htmlFor="registerFullName">
                            Full name
                          </label>
                          <input
                            id="registerFullName"
                            className="field-input auth-field"
                            type="text"
                            value={fullName}
                            onChange={(event) => setFullName(event.target.value)}
                            placeholder="Optional display name"
                            autoComplete="name"
                          />
                        </div>

                        <div className="field">
                          <label className="field-label" htmlFor="registerJurisdiction">
                            Initial code focus
                          </label>
                          <select
                            id="registerJurisdiction"
                            className="field-select auth-field"
                            value={jurisdiction}
                            onChange={(event) => setJurisdiction(event.target.value)}
                          >
                            <option value="">Choose later</option>
                            {jurisdictions.map((option) => (
                              <option key={option.name} value={option.name}>
                                {option.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div className="auth-field-grid">
                        <div className="field">
                          <label className="field-label" htmlFor="registerPassword">
                            Password
                          </label>
                          <input
                            id="registerPassword"
                            className="field-input auth-field"
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            placeholder="At least 8 characters"
                            required
                            autoComplete="new-password"
                          />
                        </div>

                        <div className="field">
                          <label className="field-label" htmlFor="confirmPassword">
                            Confirm password
                          </label>
                          <input
                            id="confirmPassword"
                            className="field-input auth-field"
                            type="password"
                            value={confirmPassword}
                            onChange={(event) => setConfirmPassword(event.target.value)}
                            placeholder="Confirm your password"
                            required
                            autoComplete="new-password"
                          />
                        </div>
                      </div>

                      <div className="auth-action-row">
                        <button
                          type="submit"
                          className="button button-primary"
                          disabled={isLoading || !email || !username || !password || !confirmPassword}
                        >
                          {isLoading ? "Creating workspace..." : "Create account"}
                        </button>
                        <button
                          type="button"
                          className="button button-subtle"
                          onClick={() => void handleGuestContinue()}
                          disabled={isLoading}
                        >
                          Continue as guest
                        </button>
                      </div>
                    </motion.form>
                  )}
                </AnimatePresence>
              </motion.div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
