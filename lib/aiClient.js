const OPENAI_API_URL = "https://api.openai.com/v1";

function hasOpenAiKey() {
  return Boolean(process.env.OPENAI_API_KEY);
}

function getAiProvider() {
  const provider = String(process.env.AI_PROVIDER || "auto").toLowerCase();
  if (provider === "openai" && hasOpenAiKey()) return "openai";
  if (provider === "ollama" && hasOllamaConfig()) return "ollama";
  if (provider === "local") return "local";
  if (hasOpenAiKey()) return "openai";
  if (hasOllamaConfig()) return "ollama";
  return "local";
}

function hasOllamaConfig() {
  return Boolean(process.env.OLLAMA_BASE_URL && process.env.OLLAMA_CHAT_MODEL);
}

async function createEmbedding(text) {
  const provider = getAiProvider();
  if (provider === "ollama") return createOllamaEmbedding(text);
  if (provider !== "openai") return null;

  const response = await fetch(`${OPENAI_API_URL}/embeddings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      model: process.env.OPENAI_EMBEDDING_MODEL || "text-embedding-3-small",
      input: text
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Embedding request failed: ${message}`);
  }

  const data = await response.json();
  return data.data?.[0]?.embedding || null;
}

async function createTutorAnswer({ question, chunks, documentTitle }) {
  const provider = getAiProvider();
  if (provider === "ollama") return createOllamaTutorAnswer({ question, chunks, documentTitle });
  if (provider !== "openai") return null;

  const context = chunks.map((chunk, index) => {
    return [
      `[자료 ${index + 1}]`,
      `문서: ${documentTitle}`,
      `섹션: ${chunk.sectionTitle}`,
      `내용: ${chunk.content}`
    ].join("\n");
  }).join("\n\n");

  const response = await fetch(`${OPENAI_API_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      model: process.env.OPENAI_CHAT_MODEL || "gpt-4.1-mini",
      temperature: 0.2,
      messages: [
        {
          role: "system",
          content: [
            "너는 업로드된 학습 자료만 근거로 설명하는 AI 과외 선생님이다.",
            "제공된 자료에서 확인할 수 없는 내용은 모른다고 말한다.",
            "학생이 이해하기 쉽게 단계적으로 설명한다.",
            "답변 마지막에는 참고한 섹션을 짧게 표시한다."
          ].join("\n")
        },
        {
          role: "user",
          content: `질문: ${question}\n\n관련 자료:\n${context}`
        }
      ]
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Chat request failed: ${message}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || null;
}

async function createOllamaEmbedding(text) {
  const baseUrl = process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434";
  const response = await fetch(`${baseUrl}/api/embed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: process.env.OLLAMA_EMBEDDING_MODEL || "nomic-embed-text",
      input: text
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Ollama embedding request failed: ${message}`);
  }

  const data = await response.json();
  return data.embeddings?.[0] || null;
}

async function createOllamaTutorAnswer({ question, chunks, documentTitle }) {
  const baseUrl = process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434";
  const context = chunks.map((chunk, index) => {
    return [
      `[자료 ${index + 1}]`,
      `문서: ${documentTitle}`,
      `섹션: ${chunk.sectionTitle}`,
      `내용: ${chunk.content}`
    ].join("\n");
  }).join("\n\n");

  const prompt = [
    "너는 업로드된 학습 자료만 근거로 설명하는 AI 과외 선생님이다.",
    "자료에 없는 내용은 없다고 말한다.",
    "학생이 이해하기 쉽게 단계적으로 설명한다.",
    "",
    `질문: ${question}`,
    "",
    `관련 자료:\n${context}`
  ].join("\n");

  const response = await fetch(`${baseUrl}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: process.env.OLLAMA_CHAT_MODEL || "llama3.1",
      prompt,
      stream: false,
      options: { temperature: 0.2 }
    })
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Ollama chat request failed: ${message}`);
  }

  const data = await response.json();
  return data.response || null;
}

module.exports = {
  hasOpenAiKey,
  hasOllamaConfig,
  getAiProvider,
  createEmbedding,
  createTutorAnswer
};
