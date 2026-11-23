import { Brand } from "@/components/ui";

const STEPS = ["학습 설정", "진단 평가", "맞춤 계획"];

export function OnboardingHeader({ current }: { current: 0 | 1 | 2 }) {
  return (
    <header className="onboarding-header">
      <div className="container">
        <Brand href="/" />
        <ol className="onboarding-steps" aria-label="시작 단계">
          {STEPS.map((label, index) => (
            <li
              key={label}
              className="row"
              style={{ listStyle: "none", gap: 8 }}
              aria-current={index === current ? "step" : undefined}
            >
              {index > 0 ? <span className="sep" aria-hidden="true" /> : null}
              <span className={`step-pill ${index === current ? "active" : index < current ? "done" : ""}`}>
                <b>{index < current ? "✓" : index + 1}</b>
                <span className="label">{label}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>
    </header>
  );
}
