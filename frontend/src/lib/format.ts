export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function capitalize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDistanceToNow(date: Date, options?: { addSuffix?: boolean }): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) {
    return options?.addSuffix ? `${diffSecs} seconds ago` : `${diffSecs}s`;
  }
  if (diffMins < 60) {
    return options?.addSuffix ? `${diffMins} minutes ago` : `${diffMins}m`;
  }
  if (diffHours < 24) {
    return options?.addSuffix ? `${diffHours} hours ago` : `${diffHours}h`;
  }
  return options?.addSuffix ? `${diffDays} days ago` : `${diffDays}d`;
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}