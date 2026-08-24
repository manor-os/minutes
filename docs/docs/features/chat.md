---
sidebar_position: 5
title: AI Chat
---

# AI Chat

Ask questions about any completed meeting and get AI-powered answers with streaming output.

## How to Use

1. Open a completed meeting
2. Scroll to **Ask About This Meeting**
3. Type your question and press Enter

The AI reads the meeting's transcript, summary, and key points to answer your question. Responses stream token-by-token in real-time.

## Example Questions

- "What did we decide about the launch date?"
- "Who is responsible for the design review?"
- "Summarize the budget discussion"
- "Were there any disagreements?"
- "What are the next steps?"

## How It Works

Your question + meeting context (transcript, summary, key points) are sent to the configured LLM:
- **Cloud mode**: OpenAI or OpenRouter
- **Local mode**: Ollama (streaming via `/api/generate`)

The response streams back via Server-Sent Events (SSE).
