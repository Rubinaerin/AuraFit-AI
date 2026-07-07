import React from "react";

export default function ScoreRing({ score, size = 96, strokeWidth = 8, label }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, score ?? 0));
  const offset = circumference - (progress / 100) * circumference;

  // utils/format bağımlılığı olmadan dinamik renk eşikleri
  let color = "#55556A"; // varsayılan gri
  if (score != null) {
    if (score >= 80) color = "#00D4AA";      // accent teal
    else if (score >= 60) color = "#FFB347"; // warning amber
    else color = "#FF4757";                  // danger red
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#2A2A3E" strokeWidth={strokeWidth} />
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={strokeWidth}
            strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.6s ease-out, stroke 0.3s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display font-semibold leading-none" style={{ fontSize: size * 0.20, color }}>
            {score != null ? Math.round(score) : "—"}
          </span>
          <span className="text-text-muted leading-none mt-0.5" style={{ fontSize: size * 0.10 }}>/ 100</span>
        </div>
      </div>
      {label && <span className="text-xs text-text-secondary font-medium text-center">{label}</span>}
    </div>
  );
}
