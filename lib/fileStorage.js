const fs = require("fs/promises");
const path = require("path");
const { getSupabaseAdmin, hasSupabaseConfig } = require("./supabaseAdmin");

const UPLOAD_DIR = path.join(process.cwd(), "uploads");

async function saveUploadedFile({ buffer, fileName, userId }) {
  const bucket = process.env.SUPABASE_STORAGE_BUCKET;

  if (hasSupabaseConfig() && bucket) {
    const supabase = getSupabaseAdmin();
    const storagePath = `${userId || "guest"}/${fileName}`;
    const { error } = await supabase.storage
      .from(bucket)
      .upload(storagePath, buffer, {
        contentType: guessContentType(fileName),
        upsert: true
      });

    if (error) throw error;

    const { data } = supabase.storage.from(bucket).getPublicUrl(storagePath);
    return {
      storedFileName: fileName,
      storagePath,
      fileUrl: data.publicUrl,
      storageProvider: "supabase"
    };
  }

  await fs.mkdir(UPLOAD_DIR, { recursive: true });
  const filePath = path.join(UPLOAD_DIR, fileName);
  await fs.writeFile(filePath, buffer);

  return {
    storedFileName: fileName,
    storagePath: filePath,
    fileUrl: `/uploads/${fileName}`,
    storageProvider: "local"
  };
}

function guessContentType(fileName) {
  const extension = path.extname(fileName || "").toLowerCase();
  return {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
  }[extension] || "application/octet-stream";
}

module.exports = {
  saveUploadedFile
};
