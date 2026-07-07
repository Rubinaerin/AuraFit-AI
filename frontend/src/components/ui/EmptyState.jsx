import React from "react";

export default function EmptyState({ icon: Icon, title, description }) {
  return (
    <div className="flex flex-col items-center justify-center text-center p-8 rounded-2xl bg-surface border border-border min-h-[300px] animate-fade-in">
      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-4">
        {Icon && <Icon size={22} />}
      </div>
      <h3 className="font-display text-lg font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-sm text-text-secondary max-w-sm leading-relaxed">{description}</p>
    </div>
  );
}