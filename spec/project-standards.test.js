import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";

const PROJECT_ROOT = new URL("..", import.meta.url);

async function readProjectFile(relativePath) {
  return readFile(new URL(relativePath, PROJECT_ROOT), "utf8");
}

async function assertRegularFile(relativePath) {
  const fileStat = await stat(new URL(relativePath, PROJECT_ROOT));
  assert.equal(fileStat.isFile(), true, `${relativePath} must be a regular file`);
}

test("repository documentation layers have active entrypoints and current review records", async () => {
  await Promise.all([
    assertRegularFile("AGENTS.md"),
    assertRegularFile("LOG.md"),
    assertRegularFile("MEMORY.md"),
    assertRegularFile("LESSONS.md"),
    assertRegularFile("docs/coverage.md")
  ]);

  const [readme, architecture, log, memory, lessons, coverage] = await Promise.all([
    readProjectFile("README.md"),
    readProjectFile("docs/architecture.md"),
    readProjectFile("LOG.md"),
    readProjectFile("MEMORY.md"),
    readProjectFile("LESSONS.md"),
    readProjectFile("docs/coverage.md")
  ]);

  assert.match(readme, /\[`?AGENTS\.md`?\]\(AGENTS\.md\)/);
  assert.doesNotMatch(readme, /development-practices\.md/);
  assert.match(readme, /LOG\.md/);
  for (const adrNumber of ["0006", "0007", "0008", "0009", "0010"]) {
    assert.match(architecture, new RegExp(`ADR ${adrNumber}`));
  }
  assert.match(log, /2026-05-13/);
  assert.match(log, /ADR 0010/);
  assert.match(log, /docs\/log\/2026-05-13-project-review\.md/);
  assert.match(memory, /Current high-priority facts/);
  assert.match(lessons, /Durable lessons/);
  assert.match(coverage, /Node v22\.22\.2/);
  assert.match(coverage, /not yet enforced/);

  const logFiles = await readdir(new URL("docs/log", PROJECT_ROOT));
  assert.equal(
    logFiles.includes("2026-05-13-project-review.md"),
    true,
    "review details must live under docs/log/ and be linked from LOG.md"
  );
});

test("package scripts expose fast, extended, and documented coverage commands", async () => {
  const packageJson = JSON.parse(await readProjectFile("package.json"));
  const scripts = packageJson.scripts;

  assert.equal(scripts.test, "npm run test:fast");
  assert.match(scripts["test:fast"], /node --test/);
  assert.match(scripts["test:fast"], /test-skip-pattern/);
  assert.match(scripts["test:extended"], /node --test/);
  assert.match(scripts["test:extended"], /test-name-pattern/);
  assert.match(scripts["test:coverage"], /--experimental-test-coverage/);
});

test("accepted ADRs have matching after-action reports", async () => {
  const adrDirectory = new URL("docs/adr/", PROJECT_ROOT);
  const entries = await readdir(adrDirectory);
  const adrFiles = entries.filter((entry) => /^\d{4}-.*\.md$/.test(entry) && !entry.endsWith("-aar.md"));
  const aarFiles = new Set(entries.filter((entry) => entry.endsWith("-aar.md")));

  for (const adrFile of adrFiles) {
    const content = await readFile(join(adrDirectory.pathname, adrFile), "utf8");

    if (!/^## Status\s+Accepted/m.test(content)) {
      continue;
    }

    const expectedAar = adrFile.replace(/\.md$/, "-aar.md");
    assert.equal(aarFiles.has(expectedAar), true, `${adrFile} must have ${expectedAar}`);
  }
});
