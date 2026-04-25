export type SceneObject = {
  id: string;
  type: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  content?: string;
  label?: string;
  items?: string[];
  table?: {
    headers: string[];
    rows: string[][];
  };
  delayMs?: number;
  graph?: {
    xMin: number;
    xMax: number;
    yMin: number;
    yMax: number;
    curves: Array<{ color: string; points: Array<[number, number]> }>;
    marks: Array<{ x: number; y: number; label: string }>;
  };
};

export type AuthSession = {
  userId: string;
  email: string;
  displayName: string;
};

export type Scene = {
  id: string;
  title: string;
  narration: string;
  objects: SceneObject[];
  resumeLabel?: string;
  teachingGoal?: string;
  takeaway?: string;
  examCue?: string;
  practiceBridge?: string;
  autoAdvanceSeconds?: number;
  sceneGroup?: string;
  branchKey?: string;
  branchLabel?: string;
};

export type DiagnosticQuestion = {
  id: string;
  prompt: string;
  options: string[];
  answer: number;
  concept: string;
  difficulty?: string;
  unitTitle?: string;
};

export type SubjectTargets = {
  korean: number;
  math: number;
  english: number;
  inquiry1: number;
  inquiry2: number;
};

export type Profile = {
  nickname: string;
  name?: string;
  exam_date?: string;
  examDate: string;
  subject_targets?: SubjectTargets;
  subjectTargets: SubjectTargets;
  target_score?: number;
  targetScore?: number;
  weekly_study_hours?: number;
  weeklyStudyHours: number;
  daily_minutes?: number;
  dailyMinutes: number;
  weak_units?: string[];
  weakUnits: string[];
  study_mood?: string;
  studyMood: string;
};

export type Task = {
  id: string;
  title: string;
  type: string;
  minutes: number;
  status: string;
  launch?: {
    mode: string;
    href: string;
    ctaLabel: string;
    bundleId?: string;
    lessonId?: string;
    problemSetId?: string;
    problemId?: string;
  };
};

export type PlanDay = {
  date: string;
  label: string;
  theme: string;
  focus: string;
  tasks: Task[];
  minutes_target?: number;
  minutesTarget: number;
};

export type Mastery = {
  id: string;
  title: string;
  score: number;
  trend: string;
  risk: string;
  label?: string;
};

export type Theme = {
  id: string;
  name: string;
  description: string;
  xpRequired: number;
};

export type Gamification = {
  streakDays: number;
  bestStreakDays?: number;
  lastActivityDate: string;
  xp: number;
  level: number;
  focusPoints?: number;
  focusLevel?: number;
  recoveryTokens?: number;
  lessonCompletions?: number;
  practiceAttempts?: number;
  solvedAttempts?: number;
  reviewSessions?: number;
  questionCount?: number;
  todayFlow?: {
    date: string;
    steps: Array<{ id: string; title: string; done: boolean }>;
    completedCount: number;
    coreCompleted: boolean;
    pointsEarned: number;
  };
  weeklyRhythm?: {
    activeDays: number;
    strongDays: number;
    totalPoints: number;
    bestStreakDays: number;
  };
  milestones?: Array<{
    id: string;
    title: string;
    description: string;
    progress: number;
    target: number;
    unlocked: boolean;
  }>;
  currentGoal?: {
    title: string;
    description: string;
    progress: number;
    target: number;
  } | null;
  activeThemeId: string;
  unlockedThemes: Theme[];
  recentUnlocks: string[];
  nextTheme?: Theme | null;
};

export type MistakeNote = {
  id: string;
  problem_id?: string;
  problemId: string;
  problem_title?: string;
  problemTitle: string;
  mistake_type?: string;
  mistakeType: string;
  trigger_step?: string;
  triggerStep: string;
  summary: string;
  correction: string;
  retry_prompt?: string;
  retryPrompt: string;
  created_at?: string;
  createdAt: string;
};

export type DashboardResponse = {
  headline: string;
  diagnosticCompleted?: boolean;
  stats: {
    daysLeft: number;
    targetScore: number;
    todayMinutes: number;
    completedTasks: number;
    readiness: number;
    weeklyStudyHours: number;
  };
  mastery: Mastery[];
  todayPlan: PlanDay;
  weeklyPlan: PlanDay[];
  planHorizonDays: number;
  todayMission: {
    headline: string;
    summary: string;
    activeTrack: string;
    recommendedUnit: string;
    currentTask?: Task | null;
    queue: Task[];
    weakUnits: string[];
  };
  activeContent?: {
    bundleId: string;
    lessonId: string;
    lessonTitle: string;
    problemSetId: string;
    problemSetTitle: string;
    problemCount: number;
    currentProblemId: string;
    currentProblemTitle: string;
    evaluationType: string;
  };
  contentLibrary: {
    bundles: Array<{
      bundleId: string;
      title: string;
      version: string;
      domain: string;
      lessonPackCount: number;
      problemSetCount: number;
      diagnosticQuestionCount: number;
      curriculum?: {
        courses: Array<{
          courseId: string;
          courseTitle: string;
          domains: Array<{
            unitId: string;
            domainTitle: string;
            contentElements?: string[];
            drillLessonPackId?: string;
            drillProblemSetId?: string;
            drillProblemCount?: number;
          }>;
        }>;
        killerTracks?: Array<{
          trackId: string;
          title: string;
          lessonPackId: string;
          problemSetId: string;
          problemCount: number;
        }>;
      };
      lessonPacks: Array<{
        id: string;
        title: string;
        unitTitle: string;
        conceptIds: string[];
      }>;
      problemSets: Array<{
        id: string;
        title: string;
        lessonPackId: string;
        problemCount: number;
        evaluationTypes: string[];
      }>;
    }>;
  };
  gamification: Gamification;
  recentMistakes: MistakeNote[];
  alerts: string[];
  coachMessage: string;
  planStrategy?: {
    headline: string;
    coachMessage: string;
    weeklyFocus: string[];
    monthlyFocus: string[];
    adaptationRules: string[];
    provider: string;
  };
  planStrategyStatus?: string;
  strategyJobs?: Array<{
    id: string;
    status: string;
    reason: string;
    queuedAt: string;
    finishedAt?: string;
    provider?: string;
  }>;
  session: {
    sessionId: string;
    companionCode: string;
    eventStreamPath: string;
  };
};

export type BootstrapResponse = {
  app: { name: string; tagline: string };
  profile: Profile;
  diagnosticQuestions: DiagnosticQuestion[];
  onboarding?: {
    surveyCompleted: boolean;
    surveyStep: number;
    diagnosticCompleted: boolean;
    diagnosticAnswers: Record<string, number>;
    requiredRoute: string;
  };
  dashboard?: DashboardResponse | null;
  contentCatalog?: {
    bundles: Array<{
      bundleId: string;
      title: string;
      version: string;
      domain: string;
      lessonPackCount: number;
      problemSetCount: number;
      diagnosticQuestionCount: number;
      curriculum?: {
        courses: Array<{
          courseId: string;
          courseTitle: string;
          domains: Array<{
            unitId: string;
            domainTitle: string;
            contentElements?: string[];
            drillLessonPackId?: string;
            drillProblemSetId?: string;
            drillProblemCount?: number;
          }>;
        }>;
        killerTracks?: Array<{
          trackId: string;
          title: string;
          lessonPackId: string;
          problemSetId: string;
          problemCount: number;
        }>;
      };
      lessonPacks: Array<{
        id: string;
        title: string;
        unitTitle: string;
        conceptIds: string[];
      }>;
      problemSets: Array<{
        id: string;
        title: string;
        lessonPackId: string;
        problemCount: number;
        evaluationTypes: string[];
      }>;
    }>;
  };
  theme?: {
    gamification: Gamification;
    themeCatalog: Theme[];
  };
  lessonPreview?: {
    title: string;
    sceneCount: number;
    practiceProblemId: string;
    problemSetId?: string;
    problemSetTitle?: string;
    problemCount?: number;
    evaluationType?: string;
    sessionId: string;
    companionCode: string;
  };
  latestAttempt?: Attempt | null;
};

export type LessonSessionResponse = {
  sessionId: string;
  unitTitle: string;
  teacherName: string;
  scenes: Scene[];
  outline: Array<{ id: string; title: string }>;
  questionStarters: string[];
  practiceProblem: {
    id: string;
    title: string;
    statement: string;
    coachHint: string;
    expectedOutline: string[];
    functionSpec: { expression: string; pointX?: number };
    evaluationType: string;
    stepGuide: Array<{ label: string; placeholder: string }>;
    finalPrompt: string;
    difficulty?: string;
    problemType?: string;
    isKiller?: boolean;
  };
  problemSet?: {
    id: string;
    bundleId: string;
    lessonPackId: string;
    title: string;
    problemCount: number;
    problemTitles: string[];
    evaluationTypes: string[];
    problems: Array<{
      id: string;
      title: string;
      statement: string;
      coachHint: string;
      expectedOutline: string[];
      evaluationType: string;
      finalPrompt: string;
      difficulty?: string;
      problemType?: string;
      isKiller?: boolean;
    }>;
  };
  branchScenes?: Array<{ id: string; title: string; branchLabel?: string; problemId?: string }>;
  realtime: {
    wsPath: string;
    companionCode: string;
  };
  experience: {
    immersiveDefault: boolean;
    llmAnswering: boolean;
    autoAdvanceSeconds?: number;
  };
};

export type StepFeedback = {
  id: string;
  label: string;
  accepted: boolean;
  reason: string;
  expected: string;
  error_type?: string;
  errorType?: string;
};

export type Attempt = {
  id: string;
  problem_id?: string;
  problemId: string;
  solved: boolean;
  score: number;
  evaluated_steps?: StepFeedback[];
  evaluatedSteps: StepFeedback[];
  submitted: {
    stepOne: string;
    stepTwo: string;
    stepThree: string;
    scratchNote?: string;
    finalAnswer: string;
  };
  summary: string;
  recommended_scenes?: string[];
  recommendedScenes: string[];
  recovery_plan?: {
    today: PlanDay;
    tomorrow?: PlanDay;
    coachMessage: string;
  };
  recoveryPlan: {
    today: PlanDay;
    tomorrow?: PlanDay;
    coachMessage: string;
  };
  created_at?: string;
  createdAt?: string;
};

export type ReviewResponse = {
  empty: boolean;
  headline: string;
  message?: string;
  attemptId?: string;
  solved?: boolean;
  summary?: string;
  wrongSteps?: StepFeedback[];
  goodSteps?: StepFeedback[];
  retrySet?: string[];
  tomorrowPlan?: PlanDay | null;
  nextProblem?: {
    nextProblemId: string;
    nextProblemTitle: string;
  } | null;
  mistakeNotes?: MistakeNote[];
};

export type LessonQuestionResponse = {
  mode: string;
  responseMode?: string;
  scene: Scene;
  branchScenes?: Scene[];
  continuationPlan?: {
    mode: string;
    orderedSceneIds: string[];
    prioritizedSceneIds: string[];
  };
  teacherReply: string;
  focusObjectId?: string | null;
  llmSource: string;
  resumeLabel?: string;
  syncEvent: Record<string, unknown>;
};

export type ThemeResponse = {
  gamification: Gamification;
  themeCatalog: Theme[];
};
