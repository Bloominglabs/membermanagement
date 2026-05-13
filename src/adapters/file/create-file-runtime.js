import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { createDocumentRuntime } from "../store/create-document-runtime.js";
import { createDefaultDocument, normalizeDocument } from "../store/default-document.js";

// File runtime is the single-instance durable adapter. It persists the same
// document shape as in-memory mode and uses atomic renames to reduce the chance
// of leaving a partially written JSON file after a crash.
function documentsEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

async function ensureDocumentExists(dataFilePath) {
  await mkdir(dirname(dataFilePath), { recursive: true });

  try {
    const fileContents = await readFile(dataFilePath, "utf8");
    const parsedDocument = JSON.parse(fileContents);
    const normalizedDocument = normalizeDocument(parsedDocument);

    if (!documentsEqual(parsedDocument, normalizedDocument)) {
      await writeDocumentAtomically(dataFilePath, normalizedDocument);
    }

    return normalizedDocument;
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }

    const defaultDocument = createDefaultDocument();
    await writeFile(dataFilePath, JSON.stringify(defaultDocument, null, 2));
    return defaultDocument;
  }
}

async function ensureDocumentWithSeed(dataFilePath, initialDocument) {
  // A caller-provided seed is only used for first creation. Existing files are
  // treated as the source of truth so restarts do not overwrite local state.
  await mkdir(dirname(dataFilePath), { recursive: true });

  try {
    const fileContents = await readFile(dataFilePath, "utf8");
    const parsedDocument = JSON.parse(fileContents);
    const normalizedDocument = normalizeDocument(parsedDocument);

    if (!documentsEqual(parsedDocument, normalizedDocument)) {
      await writeDocumentAtomically(dataFilePath, normalizedDocument);
    }

    return normalizedDocument;
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }

    const document = normalizeDocument(initialDocument ?? createDefaultDocument());
    await writeFile(dataFilePath, JSON.stringify(document, null, 2));
    return document;
  }
}

async function writeDocumentAtomically(dataFilePath, document) {
  const temporaryPath = `${dataFilePath}.tmp`;
  await writeFile(temporaryPath, JSON.stringify(document, null, 2));
  await rename(temporaryPath, dataFilePath);
}

export async function createFileRuntime({
  dataFilePath,
  allowedOrigins = [],
  clock,
  initialDocument,
  sessionLifetimeMinutes
}) {
  const document = initialDocument
    ? await ensureDocumentWithSeed(dataFilePath, initialDocument)
    : await ensureDocumentExists(dataFilePath);

  return createDocumentRuntime({
    document,
    allowedOrigins,
    clock,
    sessionLifetimeMinutes,
    persistDocument: async (nextDocument) => {
      await writeDocumentAtomically(dataFilePath, nextDocument);
    }
  });
}
