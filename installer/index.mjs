#!/usr/bin/env node

import { execSync, spawn } from "child_process";
import { createInterface } from "readline";
import { writeFileSync, existsSync, mkdirSync } from "fs";
import { join } from "path";

const REPO = "https://github.com/manor-os/minutes.git";
const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const DIM = "\x1b[2m";
const BOLD = "\x1b[1m";
const RESET = "\x1b[0m";

const log = (msg) => console.log(msg);
const info = (msg) => log(`${CYAN}>${RESET} ${msg}`);
const success = (msg) => log(`${GREEN}>${RESET} ${msg}`);
const warn = (msg) => log(`${YELLOW}>${RESET} ${msg}`);
const error = (msg) => log(`${RED}>${RESET} ${msg}`);

function banner() {
  log("");
  log(`${BOLD}  Minutes${RESET} ${DIM}— AI Meeting Transcription${RESET}`);
  log(`${DIM}  Powered by Manor AI${RESET}`);
  log("");
}

function check(cmd, name) {
  try {
    execSync(`${cmd}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function ask(rl, question, defaultVal = "") {
  const suffix = defaultVal ? ` ${DIM}(${defaultVal})${RESET}` : "";
  return new Promise((resolve) => {
    rl.question(`${CYAN}?${RESET} ${question}${suffix}: `, (answer) => {
      resolve(answer.trim() || defaultVal);
    });
  });
}

async function main() {
  banner();

  const args = process.argv.slice(2);
  const dirName = args[0] || "minutes";

  // Check prerequisites
  info("Checking prerequisites...");

  if (!check("docker --version", "Docker")) {
    error("Docker is required. Install from https://docker.com");
    process.exit(1);
  }

  if (!check("docker compose version", "Docker Compose")) {
    if (!check("docker-compose --version", "docker-compose")) {
      error("Docker Compose is required. Install from https://docker.com");
      process.exit(1);
    }
  }

  if (!check("git --version", "Git")) {
    error("Git is required. Install from https://git-scm.com");
    process.exit(1);
  }

  success("Docker, Docker Compose, and Git found");

  const rl = createInterface({ input: process.stdin, output: process.stdout });

  // Choose mode
  log("");
  log(`${BOLD}  Choose your setup:${RESET}`);
  log("");
  log(`  ${BOLD}1${RESET}  ${GREEN}Local${RESET}      — No API keys needed. Uses local AI models.`);
  log(`                  ${DIM}Requires ~6GB RAM for Ollama + faster-whisper${RESET}`);
  log(`  ${BOLD}2${RESET}  ${CYAN}Cloud API${RESET}  — Use OpenAI Whisper + OpenRouter/OpenAI for summarization.`);
  log(`                  ${DIM}Better accuracy, requires API key${RESET}`);
  log(`  ${BOLD}3${RESET}  ${YELLOW}Custom${RESET}     — Configure everything manually.`);
  log("");

  const mode = await ask(rl, "Select mode [1/2/3]", "1");

  let envContent = "";
  let composeFiles = "docker-compose.yml";

  if (mode === "1") {
    // Fully local
    composeFiles = "docker-compose.yml -f docker-compose.local.yml";
    envContent = [
      "# Minutes — Local Mode (no API keys needed)",
      "EDITION=community",
      "AUTH_MODE=local",
      "STT_MODE=local",
      "LLM_MODE=local",
      "STORAGE_BACKEND=minio",
      "JWT_SECRET=" + randomSecret(),
      "",
    ].join("\n");
    success("Local mode — no API keys needed");

  } else if (mode === "2") {
    // Cloud API
    log("");
    const sttKey = await ask(rl, "OpenAI API key (for Whisper transcription)");
    const llmKey = await ask(rl, "OpenRouter or OpenAI API key (for summarization)", sttKey);

    composeFiles = "docker-compose.yml";
    envContent = [
      "# Minutes — Cloud API Mode",
      "EDITION=community",
      "AUTH_MODE=local",
      "STORAGE_BACKEND=minio",
      `OPENAI_API_KEY=${sttKey}`,
      `OPENROUTER_API_KEY=${llmKey}`,
      "JWT_SECRET=" + randomSecret(),
      "",
    ].join("\n");
    success("Cloud API mode configured");

  } else {
    // Custom
    composeFiles = "docker-compose.yml";
    envContent = [
      "# Minutes — Custom Configuration",
      "# Edit this file to configure your setup",
      "EDITION=community",
      "AUTH_MODE=local",
      "STORAGE_BACKEND=minio",
      "",
      "# Speech-to-Text (cloud or local)",
      "# STT_MODE=local",
      "# WHISPER_MODEL_SIZE=base",
      "OPENAI_API_KEY=your-openai-key",
      "",
      "# LLM for summarization (cloud or local)",
      "# LLM_MODE=local",
      "# OLLAMA_URL=http://ollama:11434",
      "# OLLAMA_MODEL=qwen2.5:3b",
      "OPENROUTER_API_KEY=your-openrouter-key",
      "",
      "JWT_SECRET=" + randomSecret(),
      "",
    ].join("\n");
    warn("Custom mode — edit .env before starting");
  }

  rl.close();

  // Clone repo
  log("");
  info(`Cloning into ./${dirName}...`);

  const targetDir = join(process.cwd(), dirName);
  if (existsSync(targetDir)) {
    error(`Directory ${dirName} already exists. Choose a different name or remove it.`);
    process.exit(1);
  }

  try {
    execSync(`git clone --depth 1 ${REPO} ${dirName}`, { stdio: "inherit" });
  } catch {
    error("Failed to clone repository. Check your internet connection.");
    process.exit(1);
  }

  // Write .env
  writeFileSync(join(targetDir, ".env"), envContent);
  success(".env configured");

  // Start services
  log("");
  info("Starting Minutes...");
  log(`${DIM}  This may take a few minutes on first run (downloading images)${RESET}`);
  log("");

  try {
    execSync(
      `docker compose -f ${composeFiles.split(" -f ").join(" -f ")} up -d`,
      { cwd: targetDir, stdio: "inherit" }
    );
  } catch {
    error("Failed to start services. Check Docker is running.");
    log(`${DIM}  You can start manually: cd ${dirName} && docker compose -f ${composeFiles} up -d${RESET}`);
    process.exit(1);
  }

  // Done
  log("");
  log(`${GREEN}${BOLD}  Minutes is running!${RESET}`);
  log("");
  log(`  ${BOLD}App:${RESET}         http://localhost:9002`);
  log(`  ${BOLD}API:${RESET}         http://localhost:8002`);
  log(`  ${BOLD}MinIO:${RESET}       http://localhost:9011  ${DIM}(minioadmin/minioadmin)${RESET}`);
  if (mode === "1") {
    log(`  ${BOLD}Ollama:${RESET}      http://localhost:11434`);
  }
  log("");
  log(`  ${DIM}cd ${dirName}${RESET}`);
  log(`  ${DIM}./minutes status    # service status${RESET}`);
  log(`  ${DIM}./minutes logs      # view logs${RESET}`);
  log(`  ${DIM}./minutes stop      # stop all${RESET}`);
  log(`  ${DIM}./minutes health    # health check${RESET}`);
  log(`  ${DIM}./minutes update    # pull latest & restart${RESET}`);
  log(`  ${DIM}./minutes backup    # backup database${RESET}`);
  log(`  ${DIM}./minutes help      # all commands${RESET}`);
  log("");
}

function randomSecret() {
  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let result = "";
  for (let i = 0; i < 48; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
