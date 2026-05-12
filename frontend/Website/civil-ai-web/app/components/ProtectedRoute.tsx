"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "../context/AuthContext";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname ?? "/chat")}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  if (isLoading || !isAuthenticated) {
    return (
      <main className="app-shell">
        <section className="page-frame">
          <div className="glass-card center-card">
            <span className="eyebrow">Civil AI</span>
            <h1 className="section-title">Restoring your session</h1>
            <p className="section-copy">Verifying your account and rebuilding the workspace.</p>
            <div className="spinner-row">
              <span className="spinner" />
              <span className="muted-label">Loading secure workspace</span>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return <>{children}</>;
}
