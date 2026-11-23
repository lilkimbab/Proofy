"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { OnboardingHeader } from "@/components/onboarding-header";
import { Progress } from "@/components/ui";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";

type SurveyStep = 0 | 1 | 2 | 3 | 4 | 5;

const TOTAL_STEPS = 6;

const STEP_COPY: Record<SurveyStep, { title: string; lead: string }> = {
  0: { title: "이름을 알려 주세요", lead: "강의와 피드백에 표시돼요." },
  1: { title: "수능 날짜를 확인해 주세요", lead: "남은 기간에 맞춰 학습 계획을 짜요." },
  2: { title: "목표 점수를 입력해 주세요", lead: "원점수 기준이에요. 학습 계획은 수학 목표 점수에 맞춰 세워요." },
  3: { title: "공부 시간을 알려 주세요", lead: "하루 학습량을 정할 때 써요." },
  4: { title: "어떤 강의가 잘 맞나요?", lead: "설명의 길이와 속도를 맞춰요." },
  5: { title: "자신 없는 단원을 골라 주세요", lead: "여러 개 골라도 돼요. 진단 결과와 함께 첫 강의를 정해요." },
};

const MOODS = [
  { value: "실전 위주", desc: "개념은 짧게, 문제 위주로" },
  { value: "기본기 재정비", desc: "정의부터 차근차근" },
  { value: "짧고 압축된 설명", desc: "핵심만 빠르게" },
  { value: "천천히 반복", desc: "같은 개념을 여러 번" },
];

const UNIT_OPTIONS = [
  "다항식",
  "방정식과 부등식",
  "도형의 방정식",
  "지수·로그",
  "삼각함수",
  "수열",
  "극한",
  "미분",
  "적분",
  "확률",
  "통계",
  "이차곡선",
  "벡터",
];

const TARGET_FIELDS = [
  { key: "targetKorean", label: "국어" },
  { key: "targetMath", label: "수학", main: true },
  { key: "targetEnglish", label: "영어" },
  { key: "targetInquiry1", label: "탐구Ⅰ" },
  { key: "targetInquiry2", label: "탐구Ⅱ" },
] as const;

function daysUntil(dateString: string): number | null {
  if (!dateString) return null;
  const target = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

export default function SurveyPage() {
  const router = useRouter();
  const { ready, bootstrap, session } = useAuthGuard({
    requireDiagnostic: false,
    redirectIfDiagnosticDone: true,
  });
  const [surveyStep, setSurveyStep] = useState<SurveyStep>(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const profile = bootstrap?.profile;
  const examDate = profile?.examDate ?? profile?.exam_date ?? "2026-11-19";
  const subjectTargets = profile?.subjectTargets ?? profile?.subject_targets ?? {
    korean: 82,
    math: profile?.targetScore ?? profile?.target_score ?? 88,
    english: 80,
    inquiry1: 78,
    inquiry2: 78,
  };
  const weeklyStudyHours = profile?.weeklyStudyHours ?? profile?.weekly_study_hours ?? 18;
  const dailyMinutes = profile?.dailyMinutes ?? profile?.daily_minutes ?? 120;
  const weakUnits = profile?.weakUnits ?? profile?.weak_units ?? ["미분"];
  // Compare as a string: the fallback array literal is a new object every render,
  // which previously made the sync effect below loop forever (Maximum update depth exceeded).
  const weakUnitsText = weakUnits.join(", ");
  const studyMood = profile?.studyMood ?? profile?.study_mood ?? "실전 위주";
  const nickname = profile?.nickname ?? profile?.name ?? session?.displayName ?? "";

  const [profileDraft, setProfileDraft] = useState({
    nickname,
    examDate,
    targetKorean: subjectTargets.korean,
    targetMath: subjectTargets.math,
    targetEnglish: subjectTargets.english,
    targetInquiry1: subjectTargets.inquiry1,
    targetInquiry2: subjectTargets.inquiry2,
    weeklyStudyHours,
    dailyMinutes,
    studyMood,
    weakUnits: weakUnitsText,
  });

  useEffect(() => {
    setProfileDraft({
      nickname,
      examDate,
      targetKorean: subjectTargets.korean,
      targetMath: subjectTargets.math,
      targetEnglish: subjectTargets.english,
      targetInquiry1: subjectTargets.inquiry1,
      targetInquiry2: subjectTargets.inquiry2,
      weeklyStudyHours,
      dailyMinutes,
      studyMood,
      weakUnits: weakUnitsText,
    });
  }, [
    dailyMinutes,
    examDate,
    nickname,
    studyMood,
    subjectTargets.english,
    subjectTargets.inquiry1,
    subjectTargets.inquiry2,
    subjectTargets.korean,
    subjectTargets.math,
    weakUnitsText,
    weeklyStudyHours,
  ]);

  useEffect(() => {
    const persistedStep = bootstrap?.onboarding?.surveyStep;
    if (typeof persistedStep === "number") {
      setSurveyStep(Math.max(0, Math.min(5, persistedStep)) as SurveyStep);
    }
  }, [bootstrap?.onboarding?.surveyStep]);

  const selectedUnits = useMemo(
    () =>
      String(profileDraft.weakUnits ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    [profileDraft.weakUnits],
  );

  function toggleUnit(unit: string) {
    const next = selectedUnits.includes(unit)
      ? selectedUnits.filter((item) => item !== unit)
      : [...selectedUnits, unit];
    setProfileDraft((current) => ({ ...current, weakUnits: next.join(", ") }));
  }

  function buildPayload(step: number, surveyCompleted: boolean) {
    return {
      nickname: profileDraft.nickname.trim(),
      examDate: profileDraft.examDate,
      subjectTargets: {
        korean: Number(profileDraft.targetKorean),
        math: Number(profileDraft.targetMath),
        english: Number(profileDraft.targetEnglish),
        inquiry1: Number(profileDraft.targetInquiry1),
        inquiry2: Number(profileDraft.targetInquiry2),
      },
      weeklyStudyHours: Number(profileDraft.weeklyStudyHours),
      dailyMinutes: Number(profileDraft.dailyMinutes),
      studyMood: profileDraft.studyMood,
      weakUnits: selectedUnits,
      surveyStep: step,
      surveyCompleted,
    };
  }

  function stepValid(step: SurveyStep) {
    switch (step) {
      case 0:
        return profileDraft.nickname.trim().length >= 1;
      case 1:
        return Boolean(profileDraft.examDate);
      case 2:
        return [
          profileDraft.targetKorean,
          profileDraft.targetMath,
          profileDraft.targetEnglish,
          profileDraft.targetInquiry1,
          profileDraft.targetInquiry2,
        ].every((value) => Number(value) >= 1);
      case 3:
        return Number(profileDraft.weeklyStudyHours) >= 1 && Number(profileDraft.dailyMinutes) >= 30;
      case 4:
        return Boolean(profileDraft.studyMood);
      case 5:
        return selectedUnits.length >= 1;
      default:
        return false;
    }
  }

  function validationMessage(step: SurveyStep) {
    switch (step) {
      case 2:
        return "모든 과목의 목표 점수를 1점 이상으로 입력해 주세요.";
      case 3:
        return "주간 1시간 이상, 하루 30분 이상으로 입력해 주세요.";
      case 5:
        return "단원을 하나 이상 골라 주세요.";
      default:
        return "답을 입력한 뒤 넘어가 주세요.";
    }
  }

  async function saveProfile() {
    if (!stepValid(5)) {
      setError(validationMessage(5));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateProfile(buildPayload(5, true));
      router.replace("/diagnostic");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "설문 저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function nextStep() {
    if (!stepValid(surveyStep)) {
      setError(validationMessage(surveyStep));
      return;
    }
    setSaving(true);
    setError(null);
    const next = Math.min(5, surveyStep + 1) as SurveyStep;
    try {
      await api.updateProfile(buildPayload(next, false));
      setSurveyStep(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "설문 저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  function prevStep() {
    setError(null);
    setSurveyStep((current) => Math.max(0, current - 1) as SurveyStep);
  }

  function renderQuestion() {
    switch (surveyStep) {
      case 0:
        return (
          <div className="field">
            <label htmlFor="nickname" className="sr-only">
              이름 또는 별명
            </label>
            <input
              id="nickname"
              className="input-lg"
              value={profileDraft.nickname}
              onChange={(event) => setProfileDraft((current) => ({ ...current, nickname: event.target.value }))}
              placeholder="이름"
              autoFocus
            />
          </div>
        );
      case 1: {
        const left = daysUntil(profileDraft.examDate);
        return (
          <div className="field">
            <label htmlFor="examDate" className="sr-only">
              시험일
            </label>
            <input
              id="examDate"
              className="input-lg"
              type="date"
              value={profileDraft.examDate}
              onChange={(event) => setProfileDraft((current) => ({ ...current, examDate: event.target.value }))}
              autoFocus
            />
            {left !== null ? (
              <p className="field-hint">
                {left >= 0 ? `D-${left}` : "지난 날짜예요. 다시 확인해 주세요."}
              </p>
            ) : null}
          </div>
        );
      }
      case 2:
        return (
          <div className="target-grid">
            {TARGET_FIELDS.map((field) => (
              <div key={field.key} className={`field ${"main" in field && field.main ? "is-main" : ""}`}>
                <label htmlFor={field.key}>{field.label}</label>
                <input
                  id={field.key}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={100}
                  value={profileDraft[field.key]}
                  onChange={(event) =>
                    setProfileDraft((current) => ({ ...current, [field.key]: Number(event.target.value) }))
                  }
                />
              </div>
            ))}
          </div>
        );
      case 3:
        return (
          <div className="grid-2">
            <div className="field">
              <label htmlFor="weeklyStudyHours">일주일 전체 공부 시간</label>
              <div className="input-suffix">
                <input
                  id="weeklyStudyHours"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  value={profileDraft.weeklyStudyHours}
                  onChange={(event) =>
                    setProfileDraft((current) => ({ ...current, weeklyStudyHours: Number(event.target.value) }))
                  }
                />
                <span>시간</span>
              </div>
            </div>
            <div className="field">
              <label htmlFor="dailyMinutes">하루 수학 공부 시간</label>
              <div className="input-suffix">
                <input
                  id="dailyMinutes"
                  type="number"
                  inputMode="numeric"
                  min={30}
                  step={10}
                  value={profileDraft.dailyMinutes}
                  onChange={(event) =>
                    setProfileDraft((current) => ({ ...current, dailyMinutes: Number(event.target.value) }))
                  }
                />
                <span>분</span>
              </div>
              <p className="field-hint">30분 이상</p>
            </div>
          </div>
        );
      case 4:
        return (
          <div className="choice-grid" role="radiogroup" aria-label="설명 스타일">
            {MOODS.map((mood) => (
              <button
                key={mood.value}
                type="button"
                role="radio"
                aria-checked={profileDraft.studyMood === mood.value}
                className={`choice-tile ${profileDraft.studyMood === mood.value ? "selected" : ""}`}
                onClick={() => setProfileDraft((current) => ({ ...current, studyMood: mood.value }))}
              >
                <strong>{mood.value}</strong>
                <span>{mood.desc}</span>
              </button>
            ))}
          </div>
        );
      case 5:
        return (
          <div className="stack">
            <div className="row" role="group" aria-label="단원 선택">
              {UNIT_OPTIONS.map((unit) => (
                <button
                  key={unit}
                  type="button"
                  className={`chip-toggle ${selectedUnits.includes(unit) ? "selected" : ""}`}
                  aria-pressed={selectedUnits.includes(unit)}
                  onClick={() => toggleUnit(unit)}
                >
                  {unit}
                </button>
              ))}
            </div>
            <div className="field">
              <label htmlFor="weakUnits">직접 입력</label>
              <input
                id="weakUnits"
                value={profileDraft.weakUnits}
                onChange={(event) => setProfileDraft((current) => ({ ...current, weakUnits: event.target.value }))}
                placeholder="예: 미분, 확률, 기하"
              />
              <p className="field-hint">쉼표로 구분해서 적어 주세요.</p>
            </div>
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <div className="onboarding">
      <OnboardingHeader current={0} />
      {!ready || !bootstrap ? (
        <div className="state" role="status">
          <div className="spinner" />
          <p>불러오는 중</p>
        </div>
      ) : (
        <main className="survey-wrap">
          <div className="survey-progress">
            <div className="meter-label">
              <span>
                질문 {surveyStep + 1} / {TOTAL_STEPS}
              </span>
              <span>1분이면 끝나요</span>
            </div>
            <Progress value={((surveyStep + 1) / TOTAL_STEPS) * 100} label="설문 진행률" />
          </div>

          <article key={surveyStep} className="card survey-card">
            <h1>{STEP_COPY[surveyStep].title}</h1>
            <p className="lead">{STEP_COPY[surveyStep].lead}</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (surveyStep < 5) void nextStep();
                else void saveProfile();
              }}
            >
              <div className="survey-body">{renderQuestion()}</div>
              {error ? (
                <p className="alert alert-error" role="alert" style={{ marginTop: 16 }}>
                  {error}
                </p>
              ) : null}
              <div className="survey-actions">
                <button
                  className="btn btn-ghost btn-lg"
                  type="button"
                  onClick={prevStep}
                  disabled={surveyStep === 0}
                >
                  이전
                </button>
                <button className="btn btn-primary btn-lg" type="submit" disabled={saving}>
                  {saving ? "저장 중..." : surveyStep < 5 ? "다음" : "진단 평가 시작"}
                </button>
              </div>
            </form>
          </article>
        </main>
      )}
    </div>
  );
}
