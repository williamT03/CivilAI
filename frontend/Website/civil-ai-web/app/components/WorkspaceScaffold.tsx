"use client";

import type { ReactNode } from "react";

import { SiteHeader } from "./SiteHeader";

interface WorkspaceScaffoldProps {
  children: ReactNode;
  mainClassName?: string;
}

export function WorkspaceScaffold({ children, mainClassName = "" }: WorkspaceScaffoldProps) {
  return (
    <div className="app-shell revamp-shell">
      <div className="page-frame scene-page-frame workspace-frame">
        <SiteHeader />
        <main className={`scene-main workspace-main ${mainClassName}`.trim()}>{children}</main>
      </div>
    </div>
  );
}
