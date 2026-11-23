const fs = require("fs/promises");
const path = require("path");
const { getSupabaseAdmin, hasSupabaseConfig } = require("./supabaseAdmin");

const DATA_DIR = path.join(process.cwd(), "data");
const DB_PATH = path.join(DATA_DIR, "study-agent.json");

const initialData = {
  documents: [],
  questions: [],
  quizzes: [],
  roadmap: [],
  attempts: []
};

async function ensureDataFile() {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(DB_PATH);
  } catch {
    await fs.writeFile(DB_PATH, JSON.stringify(initialData, null, 2), "utf-8");
  }
}

async function readDb() {
  await ensureDataFile();
  const raw = await fs.readFile(DB_PATH, "utf-8");
  return { ...initialData, ...JSON.parse(raw || "{}") };
}

async function writeDb(data) {
  await ensureDataFile();
  await fs.writeFile(DB_PATH, JSON.stringify(data, null, 2), "utf-8");
}

function createId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ""));
}

function mapDbDocument(row, sections = []) {
  return {
    id: row.id,
    userId: row.user_id,
    title: row.title,
    subject: row.subject,
    goal: row.goal,
    deadline: row.deadline,
    originalFileName: row.original_file_name,
    storedFileName: row.stored_file_name,
    storagePath: row.storage_path,
    fileUrl: row.file_url,
    storageProvider: row.storage_provider,
    status: row.status,
    progress: row.progress,
    color: row.color || "blue",
    overview: row.overview || {},
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    sections
  };
}

function mapDbSection(row, chunks = []) {
  return {
    id: row.id,
    index: row.order_index,
    title: row.title,
    content: row.content,
    keywords: row.keywords || [],
    explanation: row.explanation || {},
    chunks
  };
}

function mapDbChunk(row) {
  return {
    id: row.id,
    sectionId: row.section_id,
    sectionTitle: row.section_title,
    index: row.chunk_index,
    content: row.content,
    pageNumber: row.page_number,
    tokenEstimate: row.token_estimate,
    embeddingProvider: row.embedding_provider || "local-hash",
    embedding: row.embedding || row.embedding_json || null
  };
}

function mapDbQuestion(row) {
  return {
    id: row.id,
    userId: row.user_id,
    documentId: row.document_id,
    sectionId: row.section_id,
    documentTitle: row.document_title,
    selectedText: row.selected_text,
    anchor: row.anchor || null,
    question: row.question,
    answer: row.answer,
    sources: row.sources || [],
    mode: row.mode,
    createdAt: row.created_at
  };
}

function mapDbQuiz(row) {
  return {
    id: row.id,
    userId: row.user_id,
    documentId: row.document_id,
    documentTitle: row.document_title,
    sectionId: row.section_id,
    sectionTitle: row.section_title,
    chunkId: row.chunk_id,
    type: row.type,
    difficulty: row.difficulty,
    question: row.question,
    options: row.options || [],
    answer: row.answer,
    explanation: row.explanation,
    hint: row.hint,
    source: row.source || {},
    createdAt: row.created_at
  };
}

function mapDbAttempt(row) {
  return {
    id: row.id,
    userId: row.user_id,
    quizId: row.quiz_id,
    documentId: row.document_id,
    userAnswer: row.user_answer,
    isCorrect: row.is_correct,
    feedback: row.feedback,
    weakConcepts: row.weak_concepts || [],
    createdAt: row.created_at
  };
}

function applyUserFilter(query, userId) {
  if (!userId) return query.is("user_id", null);
  if (isUuid(userId)) return query.eq("user_id", userId);
  return query.is("user_id", null);
}

async function listDocumentsFromSupabase(userId) {
  const supabase = getSupabaseAdmin();
  const query = supabase
    .from("documents")
    .select("*")
    .order("created_at", { ascending: false });
  const { data, error } = await applyUserFilter(query, userId);

  if (error) throw error;
  return data.map((row) => mapDbDocument(row, []));
}

async function getDocumentFromSupabase(id, userId) {
  if (!isUuid(id)) return null;

  const supabase = getSupabaseAdmin();
  const documentQuery = supabase
    .from("documents")
    .select("*")
    .eq("id", id);
  const { data: document, error: documentError } = await applyUserFilter(documentQuery, userId).single();

  if (documentError) {
    if (documentError.code === "PGRST116") return null;
    throw documentError;
  }

  const { data: sections, error: sectionsError } = await supabase
    .from("document_sections")
    .select("*")
    .eq("document_id", id)
    .order("order_index", { ascending: true });

  if (sectionsError) throw sectionsError;

  const sectionIds = sections.map((section) => section.id);
  const { data: chunks, error: chunksError } = sectionIds.length
    ? await supabase
      .from("document_chunks")
      .select("*")
      .in("section_id", sectionIds)
      .order("chunk_index", { ascending: true })
    : { data: [], error: null };

  if (chunksError) throw chunksError;

  const chunksBySection = new Map();
  chunks.forEach((chunk) => {
    const list = chunksBySection.get(chunk.section_id) || [];
    list.push(mapDbChunk(chunk));
    chunksBySection.set(chunk.section_id, list);
  });

  const mappedSections = sections.map((section) => {
    const sectionChunks = chunksBySection.get(section.id) || [];
    return mapDbSection(section, sectionChunks.map((chunk) => ({
      ...chunk,
      sectionTitle: section.title
    })));
  });

  return mapDbDocument(document, mappedSections);
}

async function saveDocumentToSupabase(document) {
  const supabase = getSupabaseAdmin();
  const { data: insertedDocument, error: documentError } = await supabase
    .from("documents")
    .insert({
      user_id: isUuid(document.userId) ? document.userId : null,
      title: document.title,
      subject: document.subject,
      goal: document.goal,
      deadline: document.deadline,
      original_file_name: document.originalFileName,
      stored_file_name: document.storedFileName,
      storage_path: document.storagePath,
      file_url: document.fileUrl,
      storage_provider: document.storageProvider,
      status: document.status,
      progress: document.progress,
      color: document.color,
      overview: document.overview
    })
    .select("*")
    .single();

  if (documentError) throw documentError;

  const sectionsToInsert = (document.sections || []).map((section) => ({
    document_id: insertedDocument.id,
    order_index: section.index,
    title: section.title,
    content: section.content,
    summary: section.explanation?.summary || "",
    explanation: section.explanation || {},
    keywords: section.keywords || []
  }));

  const { data: insertedSections, error: sectionsError } = sectionsToInsert.length
    ? await supabase.from("document_sections").insert(sectionsToInsert).select("*")
    : { data: [], error: null };

  if (sectionsError) throw sectionsError;

  const sectionIdByOrder = new Map(insertedSections.map((section) => [section.order_index, section.id]));
  const chunksToInsert = [];

  (document.sections || []).forEach((section) => {
    const sectionId = sectionIdByOrder.get(section.index);
    (section.chunks || []).forEach((chunk) => {
      const chunkRecord = {
        document_id: insertedDocument.id,
        section_id: sectionId,
        chunk_index: chunk.index,
        content: chunk.content,
        page_number: chunk.pageNumber || null,
        token_estimate: chunk.tokenEstimate,
        embedding_provider: chunk.embeddingProvider,
        embedding_json: Array.isArray(chunk.embedding) ? chunk.embedding : null
      };

      if (chunk.embeddingProvider === "openai" && Array.isArray(chunk.embedding) && chunk.embedding.length === 1536) {
        chunkRecord.embedding = chunk.embedding;
      }

      chunksToInsert.push(chunkRecord);
    });
  });

  if (chunksToInsert.length) {
    let { error: chunksError } = await supabase.from("document_chunks").insert(chunksToInsert);
    if (chunksError && /embedding_json/i.test(chunksError.message || "")) {
      const legacyChunks = chunksToInsert.map(({ embedding_json, ...chunk }) => chunk);
      const retry = await supabase.from("document_chunks").insert(legacyChunks);
      chunksError = retry.error;
    }
    if (chunksError) throw chunksError;
  }

  return getDocumentFromSupabase(insertedDocument.id, document.userId);
}

async function saveQuestionToSupabase(question) {
  const supabase = getSupabaseAdmin();
  const record = {
    user_id: isUuid(question.userId) ? question.userId : null,
    document_id: isUuid(question.documentId) ? question.documentId : null,
    section_id: isUuid(question.sectionId) ? question.sectionId : null,
    document_title: question.documentTitle,
    selected_text: question.selectedText || "",
    anchor: question.anchor || null,
    question: question.question,
    answer: question.answer,
    sources: question.sources || [],
    mode: question.mode
  };

  let { data, error } = await supabase
    .from("questions")
    .insert(record)
    .select("*")
    .single();

  if (error && /section_id|selected_text|anchor/i.test(error.message || "")) {
    const legacyRecord = { ...record };
    delete legacyRecord.section_id;
    delete legacyRecord.selected_text;
    delete legacyRecord.anchor;
    const retry = await supabase
      .from("questions")
      .insert(legacyRecord)
      .select("*")
      .single();
    data = retry.data;
    error = retry.error;
  }

  if (error) throw error;
  return mapDbQuestion(data);
}

async function listQuestionsFromSupabase(userId) {
  const supabase = getSupabaseAdmin();
  const query = supabase
    .from("questions")
    .select("*")
    .order("created_at", { ascending: false });
  const { data, error } = await applyUserFilter(query, userId);

  if (error) throw error;
  return data.map(mapDbQuestion);
}

async function listAttemptsFromSupabase(userId) {
  const supabase = getSupabaseAdmin();
  const query = supabase
    .from("quiz_attempts")
    .select("*")
    .order("created_at", { ascending: false });
  const { data, error } = await applyUserFilter(query, userId);

  if (error) throw error;
  return data.map(mapDbAttempt);
}

async function saveQuizzesToSupabase(quizzes, userId) {
  const supabase = getSupabaseAdmin();
  const records = quizzes.map((quiz) => ({
    user_id: isUuid(quiz.userId || userId) ? (quiz.userId || userId) : null,
    document_id: isUuid(quiz.documentId) ? quiz.documentId : null,
    document_title: quiz.documentTitle,
    section_id: isUuid(quiz.sectionId) ? quiz.sectionId : null,
    section_title: quiz.sectionTitle,
    chunk_id: isUuid(quiz.chunkId) ? quiz.chunkId : null,
    type: quiz.type,
    difficulty: quiz.difficulty,
    question: quiz.question,
    options: quiz.options || [],
    answer: quiz.answer,
    explanation: quiz.explanation,
    hint: quiz.hint,
    source: quiz.source || {}
  }));

  const { data, error } = await supabase.from("generated_quizzes").insert(records).select("*");
  if (error) throw error;
  return data.map(mapDbQuiz);
}

async function getQuizFromSupabase(id, userId) {
  if (!isUuid(id)) return null;

  const supabase = getSupabaseAdmin();
  const query = supabase
    .from("generated_quizzes")
    .select("*")
    .eq("id", id);
  const { data, error } = await applyUserFilter(query, userId).single();

  if (error) {
    if (error.code === "PGRST116") return null;
    throw error;
  }

  return mapDbQuiz(data);
}

async function saveAttemptToSupabase(attempt) {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from("quiz_attempts")
    .insert({
      user_id: isUuid(attempt.userId) ? attempt.userId : null,
      quiz_id: isUuid(attempt.quizId) ? attempt.quizId : null,
      document_id: isUuid(attempt.documentId) ? attempt.documentId : null,
      user_answer: attempt.userAnswer,
      is_correct: attempt.isCorrect,
      feedback: attempt.feedback,
      weak_concepts: attempt.weakConcepts || []
    })
    .select("*")
    .single();

  if (error) throw error;
  return mapDbAttempt(data);
}

function filterByUser(records, userId) {
  if (!userId || userId === "guest") return records.filter((record) => !record.userId || record.userId === "guest");
  return records.filter((record) => record.userId === userId);
}

async function listDocuments(userId = "guest") {
  if (hasSupabaseConfig()) return listDocumentsFromSupabase(userId);

  const db = await readDb();
  return filterByUser(db.documents, userId).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

async function getDocument(id, userId = "guest") {
  if (hasSupabaseConfig()) return getDocumentFromSupabase(id, userId);

  const db = await readDb();
  return filterByUser(db.documents, userId).find((doc) => doc.id === id) || null;
}

async function saveDocument(document) {
  if (hasSupabaseConfig()) return saveDocumentToSupabase(document);

  const db = await readDb();
  db.documents.unshift(document);
  await writeDb(db);
  return document;
}

async function updateDocument(id, updates, userId = "guest") {
  if (hasSupabaseConfig()) {
    const supabase = getSupabaseAdmin();
    const updatePayload = {
      updated_at: new Date().toISOString()
    };

    ["title", "subject", "goal", "deadline", "status", "progress", "overview"].forEach((key) => {
      if (updates[key] !== undefined) updatePayload[key] = updates[key];
    });

    const query = supabase
      .from("documents")
      .update(updatePayload)
      .eq("id", id);
    const { error } = await applyUserFilter(query, userId);
    if (error) throw error;
    return getDocumentFromSupabase(id, userId);
  }

  const db = await readDb();
  const index = db.documents.findIndex((doc) => doc.id === id && (!userId || userId === "guest" || doc.userId === userId));
  if (index === -1) return null;
  db.documents[index] = { ...db.documents[index], ...updates, updatedAt: new Date().toISOString() };
  await writeDb(db);
  return db.documents[index];
}

async function saveQuestion(question) {
  if (hasSupabaseConfig()) return saveQuestionToSupabase(question);

  const db = await readDb();
  const record = { ...question, id: createId("q"), createdAt: new Date().toISOString() };
  db.questions.unshift(record);
  await writeDb(db);
  return record;
}

async function listQuestions(userId = "guest") {
  if (hasSupabaseConfig()) return listQuestionsFromSupabase(userId);

  const db = await readDb();
  return filterByUser(db.questions, userId).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

async function saveQuizzes(quizzes, userId = "guest") {
  if (hasSupabaseConfig()) return saveQuizzesToSupabase(quizzes, userId);

  const db = await readDb();
  const records = quizzes.map((quiz) => ({
    ...quiz,
    userId: quiz.userId || userId,
    id: quiz.id || createId("quiz"),
    createdAt: quiz.createdAt || new Date().toISOString()
  }));
  db.quizzes.unshift(...records);
  await writeDb(db);
  return records;
}

async function getQuiz(id, userId = "guest") {
  if (hasSupabaseConfig()) return getQuizFromSupabase(id, userId);

  const db = await readDb();
  return filterByUser(db.quizzes, userId).find((quiz) => quiz.id === id) || null;
}

async function saveAttempt(attempt) {
  if (hasSupabaseConfig()) return saveAttemptToSupabase(attempt);

  const db = await readDb();
  const record = {
    ...attempt,
    id: createId("attempt"),
    createdAt: new Date().toISOString()
  };
  db.attempts.unshift(record);
  await writeDb(db);
  return record;
}

async function listAttempts(userId = "guest") {
  if (hasSupabaseConfig()) return listAttemptsFromSupabase(userId);

  const db = await readDb();
  return filterByUser(db.attempts, userId).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

module.exports = {
  createId,
  listDocuments,
  getDocument,
  saveDocument,
  updateDocument,
  saveQuestion,
  listQuestions,
  saveQuizzes,
  getQuiz,
  saveAttempt,
  listAttempts,
  hasSupabaseConfig
};
