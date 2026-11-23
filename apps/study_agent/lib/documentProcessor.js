const MAX_SECTION_CHARS = 2600;
const MIN_SECTION_CHARS = 500;
const STOPWORDS = new Set([
  "그리고", "그러나", "하지만", "또한", "있는", "없는", "한다", "입니다", "대한", "위한",
  "the", "and", "for", "with", "that", "this", "from", "into", "about"
]);

function normalizeText(text) {
  return String(text || "")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function tokenize(text) {
  return normalizeText(text)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((word) => word.length > 1 && !STOPWORDS.has(word));
}

function guessTitle(block, index) {
  const firstLine = block.split("\n").map((line) => line.trim()).find(Boolean) || `섹션 ${index + 1}`;
  return firstLine.length > 42 ? `${firstLine.slice(0, 42)}...` : firstLine;
}

function splitLargeBlock(block) {
  const paragraphs = block.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  const chunks = [];
  let current = "";

  for (const paragraph of paragraphs.length ? paragraphs : [block]) {
    if ((current + "\n\n" + paragraph).length > MAX_SECTION_CHARS && current.length >= MIN_SECTION_CHARS) {
      chunks.push(current.trim());
      current = paragraph;
    } else {
      current = current ? `${current}\n\n${paragraph}` : paragraph;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function splitIntoSections(text) {
  const normalized = normalizeText(text);
  if (!normalized) return [];

  const lines = normalized.split("\n");
  const blocks = [];
  let current = [];

  const numberedHeadingPattern = /^\d+[\).\s]+.{1,60}$/;
  const headingPattern = /^(제\s*\d+\s*[장절]|[가-힣A-Za-z ]{2,32}$)/;

  lines.forEach((line) => {
    const trimmed = line.trim();
    const isHeading = trimmed.length <= 64
      && (numberedHeadingPattern.test(trimmed) || headingPattern.test(trimmed))
      && current.join("\n").trim().length > 0;
    if (isHeading) {
      blocks.push(current.join("\n").trim());
      current = [trimmed];
    } else {
      current.push(line);
    }
  });

  if (current.join("\n").trim()) blocks.push(current.join("\n").trim());

  const sections = [];
  blocks.flatMap(splitLargeBlock).forEach((content, index) => {
    const keywords = Array.from(new Set(tokenize(content))).slice(0, 12);
    sections.push({
      id: `section-${index + 1}`,
      index: index + 1,
      title: guessTitle(content, index),
      content,
      keywords,
      explanation: buildSectionExplanation(content, index)
    });
  });

  return sections;
}

function takeSentences(text, limit = 3) {
  const sentences = normalizeText(text)
    .split(/(?<=[.!?。！？])\s+|\n+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  return sentences.slice(0, limit);
}

function buildSectionExplanation(content, index) {
  const sentences = takeSentences(content, 4);
  const keywords = Array.from(new Set(tokenize(content))).slice(0, 8);

  return {
    title: guessTitle(content, index),
    summary: sentences.join(" ") || content.slice(0, 240),
    keyPoints: sentences.slice(0, 3).map((sentence) => sentence.length > 120 ? `${sentence.slice(0, 120)}...` : sentence),
    keywords,
    studyPrompt: keywords.length
      ? `${keywords.slice(0, 3).join(", ")} 개념을 중심으로 이해하고 예제에 적용해보세요.`
      : "핵심 문장을 먼저 읽고, 이해되지 않는 부분을 질문해보세요."
  };
}

function buildDocumentStudyPack(text) {
  const sections = splitIntoSections(text);
  const overview = {
    sectionCount: sections.length,
    summary: sections.map((section) => section.explanation.summary).join(" ").slice(0, 900),
    recommendedFlow: sections.map((section) => ({
      sectionId: section.id,
      title: section.title,
      task: `${section.title} 읽기, 핵심어 확인, 질문 1개 만들기`
    }))
  };

  return { sections, overview };
}

function scoreSection(section, question) {
  const questionWords = tokenize(question);
  if (!questionWords.length) return 0;

  const sectionWords = new Set(tokenize(`${section.title} ${section.content} ${section.keywords.join(" ")}`));
  return questionWords.reduce((score, word) => score + (sectionWords.has(word) ? 1 : 0), 0);
}

function retrieveRelevantSections(sections, question, limit = 3) {
  return [...sections]
    .map((section) => ({ section, score: scoreSection(section, question) }))
    .sort((a, b) => b.score - a.score)
    .filter((item, index) => item.score > 0 || index < 1)
    .slice(0, limit)
    .map((item) => item.section);
}

function composeLocalAnswer(question, sections) {
  if (!sections.length) {
    return {
      answer: "업로드된 자료에서 관련 내용을 찾지 못했습니다. 질문을 조금 더 구체적으로 작성해보세요.",
      sources: []
    };
  }

  const sourceSummaries = sections.map((section) => {
    const points = section.explanation.keyPoints.length
      ? section.explanation.keyPoints.join(" ")
      : section.content.slice(0, 260);
    return `${section.title}: ${points}`;
  });

  return {
    answer: `자료에서 관련성이 높은 섹션을 기준으로 설명할게요.\n\n${sourceSummaries.join("\n\n")}\n\n질문한 내용은 위 섹션의 핵심 개념과 연결됩니다. 먼저 핵심 문장을 읽고, 이어서 예시나 문제에 적용해보면 이해가 더 잘 됩니다.`,
    sources: sections.map((section) => ({
      sectionId: section.id,
      title: section.title,
      index: section.index
    }))
  };
}

module.exports = {
  normalizeText,
  tokenize,
  splitIntoSections,
  buildDocumentStudyPack,
  retrieveRelevantSections,
  composeLocalAnswer
};
