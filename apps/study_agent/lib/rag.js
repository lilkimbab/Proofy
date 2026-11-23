const { createEmbedding, createTutorAnswer, getAiProvider } = require("./aiClient");
const { composeLocalAnswer, tokenize } = require("./documentProcessor");

const EMBEDDING_DIMENSIONS = 256;
const MAX_CHUNK_CHARS = 900;
const MIN_CHUNK_CHARS = 260;

function createLocalEmbedding(text) {
  const vector = Array.from({ length: EMBEDDING_DIMENSIONS }, () => 0);
  const words = tokenize(text);

  words.forEach((word) => {
    const index = Math.abs(hashString(word)) % EMBEDDING_DIMENSIONS;
    vector[index] += 1;
  });

  return normalizeVector(vector);
}

async function createSearchEmbedding(text) {
  if (getAiProvider() !== "local") {
    try {
      const embedding = await createEmbedding(text);
      if (embedding?.length) return embedding;
    } catch (error) {
      console.warn(error.message);
    }
  }
  return createLocalEmbedding(text);
}

async function enrichSectionsWithChunks(sections) {
  const enriched = [];

  for (const section of sections) {
    const chunks = splitSectionIntoChunks(section).map((chunk, index) => ({
      id: `${section.id}-chunk-${index + 1}`,
      sectionId: section.id,
      sectionTitle: section.title,
      index: index + 1,
      content: chunk,
      tokenEstimate: estimateTokens(chunk),
      embeddingProvider: getAiProvider() === "local" ? "local-hash" : getAiProvider(),
      embedding: null
    }));

    for (const chunk of chunks) {
      chunk.embedding = await createSearchEmbedding(`${section.title}\n${chunk.content}`);
    }

    enriched.push({ ...section, chunks });
  }

  return enriched;
}

function flattenDocumentChunks(document) {
  return (document.sections || []).flatMap((section) => {
    const chunks = section.chunks?.length
      ? section.chunks
      : splitSectionIntoChunks(section).map((content, index) => ({
        id: `${section.id}-chunk-${index + 1}`,
        sectionId: section.id,
        sectionTitle: section.title,
        index: index + 1,
        content,
        embeddingProvider: "local-hash",
        embedding: createLocalEmbedding(`${section.title}\n${content}`)
      }));

    return chunks.map((chunk) => ({
      ...chunk,
      sectionTitle: chunk.sectionTitle || section.title,
      sectionIndex: section.index
    }));
  });
}

async function retrieveRelevantChunks(document, question, limit = 5) {
  const questionEmbedding = await createSearchEmbedding(question);
  const chunks = flattenDocumentChunks(document);
  const scored = [];

  for (const chunk of chunks) {
    const chunkEmbedding = chunk.embedding?.length === questionEmbedding.length
      ? chunk.embedding
      : await createSearchEmbedding(`${chunk.sectionTitle}\n${chunk.content}`);

    scored.push({
      ...chunk,
      embedding: chunkEmbedding,
      score: cosineSimilarity(questionEmbedding, chunkEmbedding)
    });
  }

  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

async function answerWithRag({ document, question }) {
  const chunks = await retrieveRelevantChunks(document, question, 5);

  if (getAiProvider() !== "local") {
    try {
      const answer = await createTutorAnswer({ question, chunks, documentTitle: document.title });
      if (answer) {
        return {
          answer,
          mode: `${getAiProvider()}-rag`,
          sources: chunksToSources(chunks)
        };
      }
    } catch (error) {
      console.warn(error.message);
    }
  }

  const sectionMap = new Map();
  chunks.forEach((chunk) => {
    if (!sectionMap.has(chunk.sectionId)) {
      sectionMap.set(chunk.sectionId, {
        id: chunk.sectionId,
        index: chunk.sectionIndex,
        title: chunk.sectionTitle,
        content: chunk.content,
        explanation: {
          keyPoints: [chunk.content.slice(0, 220)],
          summary: chunk.content.slice(0, 320)
        }
      });
    }
  });

  const local = composeLocalAnswer(question, Array.from(sectionMap.values()));
  return {
    ...local,
    mode: "local-rag",
    sources: chunksToSources(chunks)
  };
}

function splitSectionIntoChunks(section) {
  const paragraphs = String(section.content || "")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const chunks = [];
  let current = "";

  for (const paragraph of paragraphs.length ? paragraphs : [section.content || ""]) {
    if ((current + "\n\n" + paragraph).length > MAX_CHUNK_CHARS && current.length >= MIN_CHUNK_CHARS) {
      chunks.push(current.trim());
      current = paragraph;
    } else {
      current = current ? `${current}\n\n${paragraph}` : paragraph;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function chunksToSources(chunks) {
  return chunks.map((chunk) => ({
    chunkId: chunk.id,
    sectionId: chunk.sectionId,
    title: chunk.sectionTitle,
    index: chunk.sectionIndex,
    score: Number(chunk.score?.toFixed(4) || 0)
  }));
}

function estimateTokens(text) {
  return Math.ceil(String(text || "").length / 3);
}

function hashString(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}

function normalizeVector(vector) {
  const magnitude = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0)) || 1;
  return vector.map((value) => value / magnitude);
}

function cosineSimilarity(a, b) {
  if (!a?.length || !b?.length || a.length !== b.length) return 0;
  return a.reduce((sum, value, index) => sum + value * b[index], 0);
}

module.exports = {
  createLocalEmbedding,
  enrichSectionsWithChunks,
  flattenDocumentChunks,
  retrieveRelevantChunks,
  answerWithRag
};
