"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

function navClass(isActive: boolean) {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isGuest, logout, user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await logout();
      router.push("/");
    } finally {
      setIsLoggingOut(false);
    }
  }

  return (
    <header className="site-header">
      <Link href="/" className="brand-lockup">
        <div className="brand-mark">C</div>
        <div className="brand-copy">
          <span className="brand-kicker">Code answers with a paper trail</span>
          <strong>CivilAI</strong>
        </div>
      </Link>

      <nav className="site-nav" aria-label="Primary">
        <Link href="/" className={navClass(pathname === "/")}>
          Home
        </Link>
        <Link href="/chat" className={navClass(pathname?.startsWith("/chat") ?? false)}>
          Chat
        </Link>
        <Link href="/about" className={navClass(pathname?.startsWith("/about") ?? false)}>
          About
        </Link>
        <Link href="/account" className={navClass(pathname?.startsWith("/account") ?? false)}>
          Account
        </Link>
        <Link
          href="/subscription"
          className={navClass(pathname?.startsWith("/subscription") ?? false)}
        >
          Subscription
        </Link>
      </nav>

      <div className="header-actions">
        <button
          type="button"
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label="Toggle theme"
        >
          <span className="theme-toggle-mark">{theme === "dark" ? "◐" : "◑"}</span>
          <span>{theme === "dark" ? "Dark" : "Light"}</span>
        </button>

        {isAuthenticated ? (
          <>
            <div className="identity-pill">
              <span className="identity-dot" />
              <div>
                <strong>{user?.full_name || user?.username}</strong>
                <span>
                  {isGuest
                    ? user?.jurisdiction || "Guest workspace"
                    : user?.jurisdiction || "Municipal research workspace"}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="button button-secondary"
              onClick={handleLogout}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? "Signing out..." : isGuest ? "Exit guest" : "Sign out"}
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="button button-secondary">
              Sign in
            </Link>
            <Link href="/register" className="button button-primary">
              Create account
            </Link>
          </>
        )}
      </div>
    </header>
  );
}
