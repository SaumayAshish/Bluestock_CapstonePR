export function StatusPill({ value }: { value: string | boolean }) {
  const label = String(value);
  const tone = label === "active" || label === "true" ? "good" : label === "pending_approval" ? "warn" : "bad";
  return <span className={`status ${tone}`}>{label.replace("_", " ")}</span>;
}
