const fs = require("fs/promises");
const path = require("path");
const { getSupabaseAdmin, hasSupabaseConfig } = require("./supabaseAdmin");
const { createId } = require("./store");

const DATA_DIR = path.join(process.cwd(), "data");
const DB_PATH = path.join(DATA_DIR, "study-agent.json");

async function readDb() {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    const raw = await fs.readFile(DB_PATH, "utf-8");
    return { annotations: [], ...JSON.parse(raw || "{}") };
  } catch {
    return { annotations: [] };
  }
}

async function writeDb(db) {
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.writeFile(DB_PATH, JSON.stringify(db, null, 2), "utf-8");
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ""));
}

function mapDbAnnotation(row) {
  return {
    id: row.id,
    userId: row.user_id,
    documentId: row.document_id,
    sectionId: row.section_id,
    type: row.type,
    selectedText: row.selected_text,
    anchor: row.anchor || null,
    note: row.note || "",
    thread: row.thread || [],
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function filterByUser(records, userId) {
  if (!userId || userId === "guest") return records.filter((record) => !record.userId || record.userId === "guest");
  return records.filter((record) => record.userId === userId);
}

function isMissingAnnotationsTable(error) {
  return error?.code === "PGRST205" || String(error?.message || "").includes("public.annotations");
}

async function listLocalAnnotations({ userId = "guest", documentId, sectionId }) {
  const db = await readDb();
  return filterByUser(db.annotations || [], userId)
    .filter((item) => item.documentId === documentId && (!sectionId || item.sectionId === sectionId))
    .sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
}

async function createLocalAnnotation(annotation) {
  const db = await readDb();
  const record = {
    ...annotation,
    id: createId("annotation"),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  db.annotations = db.annotations || [];
  db.annotations.unshift(record);
  await writeDb(db);
  return record;
}

async function updateLocalAnnotation({ id, userId = "guest", note, threadItem }) {
  const db = await readDb();
  const index = (db.annotations || []).findIndex((item) => item.id === id && (!userId || userId === item.userId || userId === "guest"));
  if (index === -1) return null;
  const current = db.annotations[index];
  db.annotations[index] = {
    ...current,
    note: note ?? current.note,
    thread: threadItem ? [...(current.thread || []), threadItem] : current.thread || [],
    updatedAt: new Date().toISOString()
  };
  await writeDb(db);
  return db.annotations[index];
}

async function listAnnotations({ userId = "guest", documentId, sectionId }) {
  if (hasSupabaseConfig()) {
    const supabase = getSupabaseAdmin();
    let query = supabase
      .from("annotations")
      .select("*")
      .eq("document_id", documentId)
      .order("created_at", { ascending: true });

    if (sectionId) query = query.eq("section_id", sectionId);
    query = isUuid(userId) ? query.eq("user_id", userId) : query.is("user_id", null);

    const { data, error } = await query;
    if (error) {
      if (isMissingAnnotationsTable(error)) return listLocalAnnotations({ userId, documentId, sectionId });
      throw error;
    }
    return data.map(mapDbAnnotation);
  }

  return listLocalAnnotations({ userId, documentId, sectionId });
}

async function createAnnotation(annotation) {
  if (hasSupabaseConfig()) {
    const supabase = getSupabaseAdmin();
    const { data, error } = await supabase
      .from("annotations")
      .insert({
        user_id: isUuid(annotation.userId) ? annotation.userId : null,
        document_id: isUuid(annotation.documentId) ? annotation.documentId : null,
        section_id: isUuid(annotation.sectionId) ? annotation.sectionId : null,
        type: annotation.type,
        selected_text: annotation.selectedText,
        anchor: annotation.anchor || null,
        note: annotation.note || "",
        thread: annotation.thread || []
      })
      .select("*")
      .single();

    if (error) {
      if (isMissingAnnotationsTable(error)) return createLocalAnnotation(annotation);
      throw error;
    }
    return mapDbAnnotation(data);
  }

  return createLocalAnnotation(annotation);
}

async function updateAnnotation({ id, userId = "guest", note, threadItem }) {
  if (hasSupabaseConfig()) {
    const supabase = getSupabaseAdmin();
    const existingQuery = supabase.from("annotations").select("*").eq("id", id);
    const { data: existing, error: existingError } = await (isUuid(userId) ? existingQuery.eq("user_id", userId) : existingQuery.is("user_id", null)).single();
    if (existingError) {
      if (isMissingAnnotationsTable(existingError)) return updateLocalAnnotation({ id, userId, note, threadItem });
      throw existingError;
    }

    const nextThread = threadItem ? [...(existing.thread || []), threadItem] : existing.thread || [];
    const updates = {
      note: note ?? existing.note,
      thread: nextThread,
      updated_at: new Date().toISOString()
    };

    const updateQuery = supabase.from("annotations").update(updates).eq("id", id);
    const { data, error } = await (isUuid(userId) ? updateQuery.eq("user_id", userId) : updateQuery.is("user_id", null)).select("*").single();
    if (error) {
      if (isMissingAnnotationsTable(error)) return updateLocalAnnotation({ id, userId, note, threadItem });
      throw error;
    }
    return mapDbAnnotation(data);
  }

  return updateLocalAnnotation({ id, userId, note, threadItem });
}

module.exports = {
  listAnnotations,
  createAnnotation,
  updateAnnotation
};
