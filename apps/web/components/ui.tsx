"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

export function Brand({ href = "/", tone }: { href?: string; tone?: "light" }) {
  return (
    <Link href={href} className="brand" style={tone === "light" ? { color: "var(--board-ink)" } : undefined}>
      <span className="brand-mark" aria-hidden="true">
        P
      </span>
      Proofy
    </Link>
  );
}

export function LoadingState({ message }: { message: string }) {
  return (
    <section className="state" role="status" aria-live="polite">
      <div className="spinner" />
      <p>{message}</p>
    </section>
  );
}

export function ErrorState({
  title,
  message,
  action,
}: {
  title: string;
  message?: string | null;
  action?: ReactNode;
}) {
  return (
    <section className="card state-card">
      <div className="state-icon" aria-hidden="true">
        !
      </div>
      <h2>{title}</h2>
      {message ? <p className="muted">{message}</p> : null}
      {action ? <div className="row" style={{ justifyContent: "center", marginTop: 8 }}>{action}</div> : null}
    </section>
  );
}

export function Progress({
  value,
  tone,
  size,
  label,
}: {
  value: number;
  tone?: "auto" | "primary";
  size?: "sm";
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const toneClass = tone === "auto" ? scoreTone(clamped) : "";
  return (
    <div
      className={`progress ${size === "sm" ? "progress-sm" : ""} ${toneClass}`}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span style={{ "--value": `${clamped}%` } as CSSProperties} />
    </div>
  );
}

export function scoreTone(score: number): "is-low" | "is-mid" | "is-high" {
  if (score < 60) return "is-low";
  if (score < 80) return "is-mid";
  return "is-high";
}

export function initials(name?: string | null): string {
  const trimmed = (name ?? "").trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "P";
}

const DIFFICULTY_LABELS: Record<string, string> = {
  basic: "기본",
  core: "기본",
  standard: "표준",
  medium: "표준",
  advanced: "심화",
  hard: "심화",
  challenge: "도전",
  killer: "킬러",
};

export function difficultyLabel(value?: string | null): string {
  if (!value) return "표준";
  return DIFFICULTY_LABELS[value.toLowerCase()] ?? value;
}

const TASK_KIND: Record<string, { label: string; className: string }> = {
  lesson: { label: "강의", className: "lesson" },
  practice: { label: "문제", className: "practice" },
  review: { label: "복습", className: "review" },
};

export function taskKind(type: string) {
  return TASK_KIND[type] ?? { label: "학습", className: "" };
}

/**
 * Renders plain-text math from the content bundles a little more legibly:
 * x^2 → x², a_n → aₙ, sqrt(17) → √(17). Only touches unambiguous patterns.
 */
export function MathText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const source = text
    .replace(/sqrt\(/g, "√(")
    .replace(/\btheta\b/g, "θ")
    .replace(/\bpi\b/g, "π")
    .replace(/<=/g, "≤")
    .replace(/>=/g, "≥");
  const pattern = /\^(\{[^}]+\}|\([^)]{1,12}\)|-?[0-9]+|[A-Za-z])|([A-Za-z])_(\{[^}]+\}|[0-9]+|[A-Za-z](?![A-Za-z]))/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(source)) !== null) {
    if (match.index > last) parts.push(source.slice(last, match.index));
    if (match[1] !== undefined) {
      parts.push(<sup key={key++}>{stripBraces(match[1])}</sup>);
    } else {
      parts.push(match[2]);
      parts.push(<sub key={key++}>{stripBraces(match[3])}</sub>);
    }
    last = match.index + match[0].length;
  }
  if (last < source.length) parts.push(source.slice(last));
  return <>{parts}</>;
}

function stripBraces(value: string) {
  if (value.startsWith("{") && value.endsWith("}")) return value.slice(1, -1);
  if (value.startsWith("(") && value.endsWith(")")) return value.slice(1, -1);
  return value;
}
