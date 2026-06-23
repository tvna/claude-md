// Parse Mermaid blocks with the official parser and report per-block results.
//
// Refs #1597. This is the I/O worker behind scripts/scan_mermaid_syntax.py: the
// Python side extracts ```mermaid fenced blocks from docs/**/*.md and the gate
// needs the REAL Mermaid parser to prove each one renders (a bracket-balance
// heuristic is explicitly not a substitute). mermaid.parse() validates syntax
// without rendering.
//
// Why jsdom: mermaid's flowchart path calls DOMPurify.addHook at module load,
// which needs a browser DOM. Without it, every flowchart parse throws
// "DOMPurify.addHook is not a function"; a false failure, not a syntax error.
// A single jsdom window injected before importing mermaid fixes this; the DOM is
// created once and reused for every block (measured ~5s for 1489 blocks).
//
// Protocol: read a JSON array of {id, text} from stdin, write a JSON array of
// {id, ok, error} to stdout. `error` is the first line of the parser message
// when ok is false, else null. Process exit code is 0 whenever the worker ran
// to completion (including when blocks failed to parse); the Python caller
// decides the gate verdict from the results. A non-zero exit means the worker
// itself could not run (bad input, missing deps).

import { JSDOM } from "jsdom";

// Inject a DOM before importing mermaid so DOMPurify initialises against it.
const dom = new JSDOM("<!DOCTYPE html><body></body>", { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.navigator = dom.window.navigator;
globalThis.DOMParser = dom.window.DOMParser;

const { default: mermaid } = await import("mermaid");
// startOnLoad false keeps mermaid from scanning the (empty) DOM on import; parse
// does not need a render pass. Defaults otherwise; we only want syntax checks.
mermaid.initialize({ startOnLoad: false });

function firstLine(message) {
  const text = typeof message === "string" ? message : String(message);
  return text.split("\n")[0].slice(0, 300);
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function main() {
  const raw = await readStdin();
  let blocks;
  try {
    blocks = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`mermaid_parse: invalid stdin JSON: ${firstLine(err.message)}\n`);
    process.exit(2);
    return;
  }
  if (!Array.isArray(blocks)) {
    process.stderr.write("mermaid_parse: stdin JSON must be an array of {id, text}\n");
    process.exit(2);
    return;
  }

  const results = [];
  for (const block of blocks) {
    const id = block && typeof block.id === "string" ? block.id : "";
    const text = block && typeof block.text === "string" ? block.text : "";
    try {
      await mermaid.parse(text);
      results.push({ id, ok: true, error: null });
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      results.push({ id, ok: false, error: firstLine(message) });
    }
  }

  process.stdout.write(JSON.stringify(results));
}

await main();
