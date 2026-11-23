import { NextResponse } from "next/server";
import path from "path";
import { buildDocumentStudyPack, normalizeText } from "@/lib/documentProcessor";
import { enrichSectionsWithChunks } from "@/lib/rag";
import { createId, listDocuments, saveDocument } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";
import { saveUploadedFile } from "@/lib/fileStorage";

export const runtime = "nodejs";

export async function GET(request) {
  const user = await getRequestUser(request);
  const documents = await listDocuments(user.id);
  return NextResponse.json({ documents });
}

export async function POST(request) {
  const user = await getRequestUser(request);
  const formData = await request.formData();
  const file = formData.get("file");
  const title = String(formData.get("title") || file?.name || "새 학습 자료");
  const subject = String(formData.get("subject") || "기타");
  const goal = String(formData.get("goal") || "");
  const deadline = String(formData.get("deadline") || "");

  if (!file || typeof file === "string") {
    return NextResponse.json({ error: "업로드할 파일이 필요합니다." }, { status: 400 });
  }

  const id = createId("doc");
  const extension = path.extname(file.name || "").toLowerCase();
  const fileName = `${id}${extension || ".txt"}`;
  const buffer = Buffer.from(await file.arrayBuffer());
  const storedFile = await saveUploadedFile({ buffer, fileName, userId: user.id });

  const extraction = await extractText(file.name, buffer);
  const studyPack = buildDocumentStudyPack(extraction.text);
  const sections = await enrichSectionsWithChunks(studyPack.sections);

  const document = {
    id,
    userId: user.id,
    title,
    subject,
    goal,
    deadline,
    originalFileName: file.name,
    storedFileName: storedFile.storedFileName,
    storagePath: storedFile.storagePath,
    fileUrl: storedFile.fileUrl,
    storageProvider: storedFile.storageProvider,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: studyPack.sections.length ? "학습 가능" : "분석 대기",
    progress: 0,
    color: "blue",
    overview: {
      ...studyPack.overview,
      chunkCount: sections.reduce((sum, section) => sum + (section.chunks?.length || 0), 0),
      pageCount: extraction.pageCount,
      extractionMethod: extraction.method,
      ocrRequired: extraction.ocrRequired
    },
    sections,
    note: extension === ".docx" || extension === ".pptx"
      ? "현재 MVP는 DOCX/PPTX 본문 추출기가 아직 연결되지 않았습니다. 다음 단계에서 DOCX/PPTX 파서를 연결하세요."
      : ""
  };

  await saveDocument(document);
  return NextResponse.json({ document });
}

async function extractText(fileName, buffer) {
  const extension = path.extname(fileName || "").toLowerCase();
  if ([".txt", ".md", ".csv"].includes(extension)) {
    return {
      text: normalizeText(buffer.toString("utf-8")),
      pageCount: null,
      method: "plain-text",
      ocrRequired: false
    };
  }

  if (extension === ".pdf") {
    try {
      const pdfParse = (await import("pdf-parse")).default;
      const parsed = await pdfParse(buffer);
      const text = normalizeText(parsed.text);
      return {
        text: text || `${fileName}\n\n텍스트를 추출하지 못했습니다. 스캔 PDF라면 OCR 단계가 필요합니다.`,
        pageCount: parsed.numpages || null,
        method: "pdf-parse",
        ocrRequired: !text
      };
    } catch (error) {
      return {
        text: normalizeText(`
${fileName}

PDF 텍스트 추출 중 오류가 발생했습니다: ${error.message}
스캔본 PDF라면 OCR 단계가 필요합니다.

긴 자료 처리 정책:
1. 문서를 단원, 제목, 페이지 기준으로 섹션 분리합니다.
2. 각 섹션별 핵심 설명과 키워드를 생성합니다.
3. 질문이 들어오면 전체 자료가 아니라 관련 섹션만 검색합니다.
4. 사용자는 섹션별 설명을 하나씩 보거나 전체 설명 묶음으로 볼 수 있습니다.
`),
        pageCount: null,
        method: "pdf-parse-error",
        ocrRequired: true
      };
    }
  }

  return {
    text: normalizeText(`
${fileName}

이 파일은 업로드되었지만 현재 MVP 환경에서는 ${extension || "해당"} 파일의 본문 추출기가 아직 연결되지 않았습니다.
다음 구현 단계에서 DOCX는 mammoth, PPTX는 전용 파서를 연결합니다.

긴 자료 처리 정책:
1. 문서를 단원, 제목, 페이지 기준으로 섹션 분리합니다.
2. 각 섹션별 핵심 설명과 키워드를 생성합니다.
3. 질문이 들어오면 전체 자료가 아니라 관련 섹션만 검색합니다.
4. 사용자는 섹션별 설명을 하나씩 보거나 전체 설명 묶음으로 볼 수 있습니다.
`),
    pageCount: null,
    method: "unsupported-placeholder",
    ocrRequired: false
  };
}
