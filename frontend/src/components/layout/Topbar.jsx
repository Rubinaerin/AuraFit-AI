import React from "react";

export default function Topbar({ title, subtitle, actions }) {
  return (
    <header className="h-16 border-b border-border bg-surface px-6 flex items-center justify-between shrink-0">
      <div className="min-w-0">
        <h1 className="font-display text-base font-semibold text-text-primary truncate">{title}</h1>
        {subtitle && <p className="text-xs text-text-secondary truncate mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </header>
  );
}