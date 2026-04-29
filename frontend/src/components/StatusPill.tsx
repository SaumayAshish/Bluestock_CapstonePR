export function StatusPill({ value }: { value: string | boolean }) {
  const label = String(value);
  const tone = label === "active" || label === "true" ? "good" : label === "pending_approval" ? "warn" : "bad";
  const text = label
    .replace("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
  return <span className={`status ${tone}`}>{text}</span>;
}
