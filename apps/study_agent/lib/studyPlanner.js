function buildLocalRoadmap({ documents, questions, attempts }) {
  const activeDocument = documents[0];
  const sections = activeDocument?.sections || [];
  const weakConcepts = collectWeakConcepts(attempts);
  const questionTopics = collectQuestionTopics(questions);

  const plan = sections.slice(0, 7).map((section, index) => {
    const needsReview = weakConcepts.some((concept) => section.title.includes(concept) || section.content?.includes(concept));
    return {
      id: `roadmap-${index + 1}`,
      day: `Day ${index + 1}`,
      title: section.title,
      status: index === 0 ? "진행 중" : needsReview ? "복습 필요" : "예정",
      tasks: [
        "섹션 설명 읽기",
        "핵심 개념 3개 정리",
        "자료 기반 문제 3개 풀기",
        needsReview ? "오답 개념 복습" : "질문 1개 남기기"
      ],
      sectionId: section.id,
      weakConcepts: needsReview ? weakConcepts : []
    };
  });

  if (!plan.length) {
    plan.push({
      id: "roadmap-empty",
      day: "Day 1",
      title: "자료 업로드 후 학습 시작",
      status: "예정",
      tasks: ["자료 업로드", "섹션 분석 확인", "첫 질문 남기기"],
      sectionId: null,
      weakConcepts: []
    });
  }

  return {
    documentId: activeDocument?.id || null,
    documentTitle: activeDocument?.title || "학습 자료",
    goal: activeDocument?.goal || "업로드 자료 기반 개념 학습",
    progress: calculateProgress(plan),
    today: plan[0],
    plan,
    recommendations: [
      weakConcepts.length ? `${weakConcepts[0]} 개념을 복습하세요.` : "오늘 학습 섹션에서 문제를 생성해 풀어보세요.",
      questionTopics.length ? `${questionTopics[0]} 관련 질문 기록을 다시 확인하세요.` : "이해가 안 되는 문장을 선택해 질문해보세요."
    ]
  };
}

function buildLocalAnalytics({ documents, questions, attempts }) {
  const totalSections = documents.reduce((sum, doc) => sum + (doc.sections?.length || 0), 0);
  const totalChunks = documents.reduce((sum, doc) => {
    return sum + (doc.sections || []).reduce((sectionSum, section) => sectionSum + (section.chunks?.length || 0), 0);
  }, 0);
  const correctAttempts = attempts.filter((attempt) => attempt.isCorrect).length;
  const accuracy = attempts.length ? Math.round((correctAttempts / attempts.length) * 100) : 0;
  const weakConcepts = collectWeakConcepts(attempts);

  return {
    metrics: [
      { label: "문서 수", value: `${documents.length}개`, delta: "업로드 자료" },
      { label: "섹션 수", value: `${totalSections}개`, delta: "학습 단위" },
      { label: "질문 수", value: `${questions.length}개`, delta: "누적 질문" },
      { label: "정답률", value: `${accuracy}%`, delta: `${attempts.length}회 풀이` }
    ],
    totalChunks,
    weakConcepts: weakConcepts.slice(0, 3).map((concept, index) => ({
      concept,
      weaknessScore: Math.max(35, 70 - index * 10)
    })),
    studyReadiness: documents.length && totalChunks ? "학습 가능" : "자료 필요"
  };
}

function collectWeakConcepts(attempts) {
  return Array.from(new Set(
    attempts
      .filter((attempt) => !attempt.isCorrect)
      .flatMap((attempt) => attempt.weakConcepts || [])
      .filter(Boolean)
  ));
}

function collectQuestionTopics(questions) {
  return Array.from(new Set(
    questions
      .map((question) => question.sources?.[0]?.title || question.documentTitle)
      .filter(Boolean)
  ));
}

function calculateProgress(plan) {
  const completed = plan.filter((item) => item.status === "완료").length;
  return plan.length ? Math.round((completed / plan.length) * 100) : 0;
}

module.exports = {
  buildLocalRoadmap,
  buildLocalAnalytics
};
