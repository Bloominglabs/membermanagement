import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { createDocumentRuntime } from "../store/create-document-runtime.js";
import { createDefaultDocument } from "../store/default-document.js";

async function ensureDocumentExists(dataFilePath) {
  await mkdir(dirname(dataFilePath), { recursive: true });

  try {
    const fileContents = await readFile(dataFilePath, "utf8");
    return JSON.parse(fileContents);
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
  await mkdir(dirname(dataFilePath), { recursive: true });

  try {
    const fileContents = await readFile(dataFilePath, "utf8");
    return JSON.parse(fileContents);
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }

    const document = initialDocument ?? createDefaultDocument();
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
  initialDocument
}) {
  const document = initialDocument
    ? await ensureDocumentWithSeed(dataFilePath, initialDocument)
    : await ensureDocumentExists(dataFilePath);

  return createDocumentRuntime({
    document,
    allowedOrigins,
    clock,
    persistDocument: async (nextDocument) => {
      await writeDocumentAtomically(dataFilePath, nextDocument);
    }
  });
}
