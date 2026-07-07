export function scoreColor(score) {
  if (score == null) return "text-text-muted";
  if (score >= 80) return "text-accent";
  if (score >= 60) return "text-warning";
  return "text-danger";
}

export function scoreRingColor(score) {
  if (score == null) return "#55556A";
  if (score >= 80) return "#00D4AA";
  if (score >= 60) return "#FFB347";
  return "#FF4757";
}

export function formatGoal(goal) {
  if (!goal) return "—";
  return goal.replace(/_/g, " ");
}