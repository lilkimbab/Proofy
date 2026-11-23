const { flattenDocumentChunks } = require("./rag");
const { tokenize } = require("./documentProcessor");

function generateLocalQuiz(document, options = {}) {
  const count = Number(options.count || 5);
  const type = options.type || "short_answer";
  const difficulty = options.difficulty || "medium";
  const chunks = flattenDocumentChunks(document).filter((chunk) => chunk.content?.trim());
  const sourceChunks = chunks.length ? chunks : fallbackChunks(document);

  return sourceChunks.slice(0, count).map((chunk, index) => {
    const concept = pickConcept(chunk);
    const sentence = pickSentence(chunk.content);
    const answer = concept || chunk.sectionTitle || "핵심 개념";

    return {
      id: `quiz_${Date.now()}_${index + 1}`,
      documentId: document.id,
      documentTitle: document.title,
      sectionId: chunk.sectionId,
      sectionTitle: chunk.sectionTitle,
      chunkId: chunk.id,
      type,
      difficulty,
      question: buildQuestion({ type, concept, sentence, chunk, index }),
      options: type === "multiple_choice" ? buildOptions(answer, chunk) : [],
      answer,
      explanation: buildExplanation({ answer, sentence, chunk }),
      hint: `${chunk.sectionTitle} 섹션의 핵심 문장을 다시 확인해보세요.`,
      source: {
        sectionId: chunk.sectionId,
        sectionTitle: chunk.sectionTitle,
        chunkId: chunk.id
      },
      createdAt: new Date().toISOString()
    };
  });
}

function gradeLocalAttempt(quiz, userAnswer) {
  const expected = normalizeAnswer(quiz.answer);
  const submitted = normalizeAnswer(userAnswer);
  const isCorrect = expected && submitted
    ? submitted.includes(expected) || expected.includes(submitted)
    : false;

  return {
    isCorrect,
    feedback: isCorrect
      ? "맞았어요. 핵심 개념을 잘 짚었습니다."
      : `아직 조금 달라요. 정답은 "${quiz.answer}"입니다. 관련 섹션을 다시 읽고, 왜 이 개념이 핵심인지 확인해보세요.`,
    weakConcepts: isCorrect ? [] : [quiz.answer],
    reviewedSection: quiz.sectionTitle
  };
}

function buildQuestion({ type, concept, sentence, chunk, index }) {
  if (type === "multiple_choice") {
    return `"${chunk.sectionTitle}" 섹션의 핵심 개념으로 가장 알맞은 것은?`;
  }

  if (type === "ox") {
    return `OX: 다음 설명은 "${chunk.sectionTitle}" 섹션의 내용과 관련이 있다. "${sentence}"`;
  }

  if (type === "blank") {
    return `${sentence.replace(concept, "_____")}\n빈칸에 들어갈 핵심 개념을 쓰세요.`;
  }

  return `${index + 1}. "${chunk.sectionTitle}" 섹션에서 다음 설명과 가장 관련 깊은 핵심 개념을 쓰세요.\n\n${sentence}`;
}

function buildExplanation({ answer, sentence, chunk }) {
  return `"${answer}"는 "${chunk.sectionTitle}" 섹션에서 중요한 개념입니다. 자료의 핵심 문장: ${sentence}`;
}

function buildOptions(answer, chunk) {
  const distractors = Array.from(new Set(tokenize(chunk.content)))
    .filter((word) => normalizeAnswer(word) !== normalizeAnswer(answer))
    .slice(0, 3);

  return shuffle([answer, ...distractors]).slice(0, 4);
}

function pickConcept(chunk) {
  const words = tokenize(`${chunk.sectionTitle} ${chunk.content}`);
  const preferred = words.find((word) => word.length >= 3) || words[0];
  return preferred || chunk.sectionTitle;
}

function pickSentence(content) {
  const sentences = String(content || "")
    .split(/(?<=[.!?。！？])\s+|\n+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 8);

  return sentences[0] || String(content || "").slice(0, 160) || "자료의 핵심 내용을 확인하세요.";
}

function normalizeAnswer(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, "")
    .trim();
}

function fallbackChunks(document) {
  return (document.sections || []).map((section, index) => ({
    id: `${section.id || index}-chunk-1`,
    sectionId: section.id,
    sectionTitle: section.title,
    content: section.content || section.explanation?.summary || section.title
  }));
}

function shuffle(items) {
  return [...items].sort((a, b) => a.localeCompare(b));
}

module.exports = {
  generateLocalQuiz,
  gradeLocalAttempt
};
