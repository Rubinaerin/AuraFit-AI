import React from "react";

export default function Spinner({ size = 24, label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2">
      <div 
        className="animate-spin rounded-full border-2 border-primary/20 border-b-primary"
        style={{ width: size, height: size }}
      />
      {label && <span className="text-xs text-text-secondary font-medium">{label}</span>}
    </div>
  );
}