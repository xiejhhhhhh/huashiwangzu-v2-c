import { createOpencodeClient } from "../.opencode/node_modules/@opencode-ai/sdk/dist/index.js";
import { readFile } from "node:fs/promises";

function parseArgs() {
  const raw = process.argv[2] ?? "{}";
  return JSON.parse(raw);
}

function textFromParts(parts) {
  return (parts ?? [])
    .filter((part) => part?.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("");
}

function summarizeMessage(message) {
  if (!message) return null;
  return {
    id: message.info?.id,
    role: message.info?.role,
    sessionID: message.info?.sessionID,
    parentID: message.info?.parentID,
    agent: message.info?.agent,
    mode: message.info?.mode,
    providerID: message.info?.providerID ?? message.info?.model?.providerID,
    modelID: message.info?.modelID ?? message.info?.model?.modelID,
    finish: message.info?.finish,
    cost: message.info?.cost,
    tokens: message.info?.tokens,
    text: textFromParts(message.parts),
    parts: message.parts ?? [],
  };
}

function makeClient(args) {
  const headers = {};
  const password = args.password ?? process.env.OPENCODE_SERVER_PASSWORD;
  const username = args.username ?? process.env.OPENCODE_SERVER_USERNAME ?? "opencode";
  if (password) {
    headers.Authorization = `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
  }
  return createOpencodeClient({
    baseUrl: `http://${args.host ?? "127.0.0.1"}:${args.port ?? 55891}`,
    directory: args.directory,
    headers,
    responseStyle: "fields",
    throwOnError: false,
  });
}

function ensureOk(result, label) {
  if (result?.error) {
    throw new Error(`${label} failed: ${JSON.stringify(result.error)}`);
  }
  if (!result?.data) {
    throw new Error(`${label} returned no data`);
  }
  return result.data;
}

async function createOrGetSession(client, args) {
  if (args.session_id) return { id: args.session_id, reused: true };
  const created = await client.session.create({
    body: { title: args.title || "opencode-sdk" },
  });
  return { ...ensureOk(created, "session.create"), reused: false };
}

async function runPrompt(args) {
  const client = makeClient(args);
  const session = await createOrGetSession(client, args);
  const promptResult = await client.session.prompt({
    path: { id: session.id },
    body: {
      parts: [{ type: "text", text: args.prompt }],
      agent: args.agent || undefined,
      model: args.provider_id && args.model_id ? { providerID: args.provider_id, modelID: args.model_id } : undefined,
      system: args.system || undefined,
      tools: args.tools || undefined,
    },
  });
  const assistant = ensureOk(promptResult, "session.prompt");
  const messages = await client.session.messages({
    path: { id: session.id },
    query: { limit: args.limit ?? 20 },
  });
  return {
    success: true,
    transport: "sdk",
    session,
    assistant: summarizeMessage(assistant),
    messages: (messages.data ?? []).map(summarizeMessage),
  };
}

async function runPromptAsync(args) {
  const client = makeClient(args);
  const session = await createOrGetSession(client, args);
  const promptResult = await client.session.promptAsync({
    path: { id: session.id },
    body: {
      parts: [{ type: "text", text: args.prompt }],
      agent: args.agent || undefined,
      model: args.provider_id && args.model_id ? { providerID: args.provider_id, modelID: args.model_id } : undefined,
      system: args.system || undefined,
      tools: args.tools || undefined,
    },
  });
  if (promptResult?.error) {
    throw new Error(`session.promptAsync failed: ${JSON.stringify(promptResult.error)}`);
  }
  const messages = await client.session.messages({
    path: { id: session.id },
    query: { limit: args.limit ?? 20 },
  });
  return {
    success: true,
    transport: "sdk",
    async: true,
    session,
    prompt_async: promptResult.data ?? {},
    messages: (messages.data ?? []).map(summarizeMessage),
  };
}

async function dispatchLetter(args) {
  const content = await readFile(args.letter_path, "utf8");
  return runPrompt({
    ...args,
    title: args.title || args.letter_title || "opencode-sdk-letter",
    prompt: `请读取并执行下面这封任务信。任务信路径：${args.letter_path}\n\n${content}`,
  });
}

async function dispatchLetterAsync(args) {
  const content = await readFile(args.letter_path, "utf8");
  return runPromptAsync({
    ...args,
    title: args.title || args.letter_title || "opencode-sdk-letter",
    prompt: `请读取并执行下面这封任务信。任务信路径：${args.letter_path}\n\n${content}`,
  });
}

async function listMessages(args) {
  const client = makeClient(args);
  const messages = await client.session.messages({
    path: { id: args.session_id },
    query: { limit: args.limit ?? 50 },
  });
  return {
    success: !messages.error,
    transport: "sdk",
    session_id: args.session_id,
    error: messages.error,
    messages: (messages.data ?? []).map(summarizeMessage),
  };
}

async function smoke(args) {
  return runPrompt({
    ...args,
    title: args.title || "opencode-sdk-smoke",
    prompt: args.prompt || "只输出 OK，不要解释。",
  });
}

async function main() {
  const args = parseArgs();
  const action = args.action;
  if (action === "prompt") return runPrompt(args);
  if (action === "prompt_async") return runPromptAsync(args);
  if (action === "dispatch_letter") return dispatchLetter(args);
  if (action === "dispatch_letter_async") return dispatchLetterAsync(args);
  if (action === "messages") return listMessages(args);
  if (action === "smoke") return smoke(args);
  throw new Error(`unknown action: ${action}`);
}

main()
  .then((result) => {
    process.stdout.write(JSON.stringify(result, null, 2));
  })
  .catch((error) => {
    process.stdout.write(JSON.stringify({
      success: false,
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    }, null, 2));
    process.exitCode = 1;
  });
