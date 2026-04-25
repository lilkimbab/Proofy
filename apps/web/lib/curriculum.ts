import type { DashboardResponse, Mastery } from "./types";

export type TrackGroup = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  courseIds: string[];
};

export type TrackUnit = {
  unitId: string;
  domainTitle: string;
  courseId: string;
  courseTitle: string;
  contentElements: string[];
  masteryScore: number;
  masteryLabel: string;
  risk: string;
  breakthroughLessonPackId?: string;
  breakthroughProblemSetId?: string;
  breakthroughProblemCount: number;
};

export type TrackView = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  averageScore: number;
  weakUnitTitle: string;
  units: TrackUnit[];
  breakthroughProblemCount: number;
  killerLessonPackId?: string;
  killerProblemSetId?: string;
  killerProblemCount: number;
  killerTitle?: string;
};

export type TrackPlanDay = {
  date: string;
  label: string;
  theme: string;
  focus: string;
  minutesTarget: number;
  tasks: DashboardResponse["todayPlan"]["tasks"];
};

export const TRACK_GROUPS: TrackGroup[] = [
  {
    id: "common-math",
    title: "공통수학",
    subtitle: "기본 구조와 함수 감각",
    description: "다항식, 방정식, 경우의 수, 도형의 방정식, 함수와 그래프를 묶어 학습합니다.",
    courseIds: ["common-math-1", "common-math-2"],
  },
  {
    id: "algebra",
    title: "대수",
    subtitle: "지수·로그·삼각·수열",
    description: "지수함수, 로그함수, 삼각함수, 수열을 한 흐름으로 정리합니다.",
    courseIds: ["algebra"],
  },
  {
    id: "calculus",
    title: "미적분",
    subtitle: "극한, 미분, 적분",
    description: "미적분 I·II를 묶어 극한부터 활용 문제까지 이어집니다.",
    courseIds: ["calculus-1", "calculus-2"],
  },
  {
    id: "probability-statistics",
    title: "확률과 통계",
    subtitle: "경우의 수, 확률, 통계",
    description: "경우의 수와 확률, 통계를 실전형 선택 과목 흐름으로 봅니다.",
    courseIds: ["probability-statistics"],
  },
  {
    id: "geometry",
    title: "기하",
    subtitle: "이차곡선, 공간, 벡터",
    description: "이차곡선과 공간좌표, 벡터를 시각적으로 연결해 학습합니다.",
    courseIds: ["geometry"],
  },
];

function masteryMap(mastery: Mastery[]) {
  return new Map(mastery.map((item) => [item.id, item]));
}

export function curriculumBundle(dashboard: DashboardResponse) {
  return dashboard.contentLibrary.bundles.find((bundle) => bundle.bundleId === "suneung-math-curriculum-v1");
}

export function buildTrackViews(dashboard: DashboardResponse): TrackView[] {
  const bundle = curriculumBundle(dashboard);
  const courses = bundle?.curriculum?.courses ?? [];
  const killerTracks = bundle?.curriculum?.killerTracks ?? [];
  const masteryById = masteryMap(dashboard.mastery);

  return TRACK_GROUPS.map((group) => {
    const units: TrackUnit[] = courses
      .filter((course) => group.courseIds.includes(course.courseId))
      .flatMap((course) =>
        course.domains.map((domain) => {
          const mastery = masteryById.get(domain.unitId);
          return {
            unitId: domain.unitId,
            domainTitle: domain.domainTitle,
            courseId: course.courseId,
            courseTitle: course.courseTitle,
            contentElements: domain.contentElements ?? [],
            masteryScore: mastery?.score ?? 0,
            masteryLabel: mastery?.label ?? "진단 필요",
            risk: mastery?.risk ?? "미측정",
            breakthroughLessonPackId: domain.drillLessonPackId,
            breakthroughProblemSetId: domain.drillProblemSetId,
            breakthroughProblemCount: domain.drillProblemCount ?? 0,
          };
        }),
      )
      .sort((left, right) => left.masteryScore - right.masteryScore);

    const averageScore = units.length
      ? Math.round(units.reduce((sum, unit) => sum + unit.masteryScore, 0) / units.length)
      : 0;
    const killerTrack = killerTracks.find((item) => item.trackId === group.id);

    return {
      id: group.id,
      title: group.title,
      subtitle: group.subtitle,
      description: group.description,
      averageScore,
      weakUnitTitle: units[0]?.domainTitle ?? "준비 중",
      units,
      breakthroughProblemCount: units.reduce(
        (sum, unit) => sum + (unit.breakthroughProblemCount ?? 0),
        0,
      ),
      killerLessonPackId: killerTrack?.lessonPackId,
      killerProblemSetId: killerTrack?.problemSetId,
      killerProblemCount: killerTrack?.problemCount ?? 0,
      killerTitle: killerTrack?.title,
    };
  }).filter((track) => track.units.length > 0);
}

export function findTrackView(dashboard: DashboardResponse, trackId: string): TrackView | null {
  return buildTrackViews(dashboard).find((track) => track.id === trackId) ?? null;
}

export function buildTrackWeeklyPlan(
  dashboard: DashboardResponse,
  trackId: string,
): TrackPlanDay[] {
  const track = findTrackView(dashboard, trackId);
  if (!track) {
    return [];
  }

  return dashboard.weeklyPlan
    .map((day) => {
      const tasks = day.tasks.filter((task) => task.title.includes(track.title));
      return {
        date: day.date,
        label: day.label,
        theme: day.theme,
        focus: day.focus,
        minutesTarget: day.minutesTarget ?? day.minutes_target ?? 0,
        tasks,
      };
    })
    .filter((day) => day.tasks.length > 0);
}
