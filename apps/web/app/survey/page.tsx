"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";

type SurveyStep = 0 | 1 | 2 | 3 | 4 | 5;

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
    weakUnits: weakUnits.join(", "),
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
      weakUnits: weakUnits.join(", "),
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
    weakUnits,
    weeklyStudyHours,
  ]);

  useEffect(() => {
    const persistedStep = bootstrap?.onboarding?.surveyStep;
    if (typeof persistedStep === "number") {
      setSurveyStep(Math.max(0, Math.min(5, persistedStep)) as SurveyStep);
    }
  }, [bootstrap?.onboarding?.surveyStep]);

  const questionTitle = useMemo(() => {
    switch (surveyStep) {
      case 0:
        return "어떻게 불러드리면 좋을까요?";
      case 1:
        return "시험일은 언제인가요?";
      case 2:
        return "이번 목표 점수는 어느 정도인가요?";
      case 3:
        return "하루 공부 시간은 어느 정도인가요?";
      case 4:
        return "어떤 설명이 편한가요?";
      case 5:
        return "가장 약한 단원은 어디인가요?";
      default:
        return "";
    }
  }, [surveyStep]);

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
      weakUnits: String(profileDraft.weakUnits ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
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
        return profileDraft.weakUnits.trim().length >= 1;
      default:
        return false;
    }
  }

  async function saveProfile() {
    if (!stepValid(5)) {
      setError("답을 입력한 뒤 넘어가 주세요.");
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
      setError("답을 입력한 뒤 넘어가 주세요.");
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
          <div className="field survey-question-field">
            <input
              id="nickname"
              value={profileDraft.nickname}
              onChange={(event) =>
                setProfileDraft((current) => ({ ...current, nickname: event.target.value }))
              }
              placeholder="별명"
              autoFocus
            />
          </div>
        );
      case 1:
        return (
          <div className="field survey-question-field">
            <input
              id="examDate"
              type="date"
              value={profileDraft.examDate}
              onChange={(event) =>
                setProfileDraft((current) => ({ ...current, examDate: event.target.value }))
              }
              autoFocus
            />
          </div>
        );
      case 2:
        return (
          <div className="survey-multi-grid">
            <div className="field">
              <label htmlFor="targetKorean">국어</label>
              <input
                id="targetKorean"
                type="number"
                value={profileDraft.targetKorean}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, targetKorean: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="targetMath">수학</label>
              <input
                id="targetMath"
                type="number"
                value={profileDraft.targetMath}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, targetMath: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="targetEnglish">영어</label>
              <input
                id="targetEnglish"
                type="number"
                value={profileDraft.targetEnglish}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, targetEnglish: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="targetInquiry1">탐구Ⅰ</label>
              <input
                id="targetInquiry1"
                type="number"
                value={profileDraft.targetInquiry1}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, targetInquiry1: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="targetInquiry2">탐구Ⅱ</label>
              <input
                id="targetInquiry2"
                type="number"
                value={profileDraft.targetInquiry2}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, targetInquiry2: Number(event.target.value) }))
                }
              />
            </div>
          </div>
        );
      case 3:
        return (
          <div className="survey-multi-grid survey-multi-grid-wide">
            <div className="field">
              <label htmlFor="weeklyStudyHours">주간 시간</label>
              <input
                id="weeklyStudyHours"
                type="number"
                value={profileDraft.weeklyStudyHours}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, weeklyStudyHours: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="dailyMinutes">하루 시간</label>
              <input
                id="dailyMinutes"
                type="number"
                value={profileDraft.dailyMinutes}
                onChange={(event) =>
                  setProfileDraft((current) => ({ ...current, dailyMinutes: Number(event.target.value) }))
                }
              />
            </div>
          </div>
        );
      case 4:
        return (
          <div className="field survey-question-field">
            <select
              id="studyMood"
              value={profileDraft.studyMood}
              onChange={(event) =>
                setProfileDraft((current) => ({ ...current, studyMood: event.target.value }))
              }
              autoFocus
            >
              {["실전 위주", "기본기 재정비", "짧고 압축된 설명", "천천히 반복"].map((mood) => (
                <option key={mood}>{mood}</option>
              ))}
            </select>
          </div>
        );
      case 5:
        return (
          <div className="field survey-question-field">
            <input
              id="weakUnits"
              value={profileDraft.weakUnits}
              onChange={(event) =>
                setProfileDraft((current) => ({ ...current, weakUnits: event.target.value }))
              }
              placeholder="예: 미분, 확률, 기하"
              autoFocus
            />
          </div>
        );
      default:
        return null;
    }
  }

  if (!ready || !bootstrap) {
    return (
      <section className="loading-state onboarding-screen">
        <div className="spinner" />
        <p>설문 화면을 준비하는 중이에요.</p>
      </section>
    );
  }

  return (
    <section className="onboarding-screen survey-minimal-screen">
      <div className="landing-backdrop" aria-hidden="true">
        <div className="landing-ring landing-ring-one" />
        <div className="landing-ring landing-ring-two" />
      </div>

      <article className="survey-question-shell">
        <div key={surveyStep} className="survey-question-card">
          <h1>{questionTitle}</h1>
          <div className="survey-question-body">{renderQuestion()}</div>
          {error ? <p className="inline-error">{error}</p> : null}
          <div className="survey-question-actions">
            <button className="button ghost" type="button" onClick={prevStep} disabled={surveyStep === 0}>
              이전
            </button>
            {surveyStep < 5 ? (
              <button className="button primary" type="button" onClick={nextStep} disabled={saving}>
                다음
              </button>
            ) : (
              <button className="button primary" type="button" onClick={saveProfile} disabled={saving}>
                {saving ? "저장 중..." : "진단 시작"}
              </button>
            )}
          </div>
        </div>
      </article>
    </section>
  );
}
