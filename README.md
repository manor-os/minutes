<p align="center">
  <img src="docs/launch/assets/github-social-preview.png" width="100%" alt="Minutes — Meetings in. Next steps out. Open-source meeting notes by Manor AI." />
</p>

<p align="center">
  <a href="https://minutes.manorai.xyz/">Try Minutes online</a> ·
  <a href="#self-host">Self-host</a> ·
  <a href="CONTRIBUTING.md">Contribute</a> ·
  <a href="README.zh-CN.md">简体中文</a>
</p>

Minutes turns recordings into transcripts, summaries, and action items. Ask questions about a meeting, find a past decision, or share the notes. Built for founders and small teams who want less work after a call.

Use the [hosted app](https://minutes.manorai.xyz/) with your Manor account, or run the MIT-licensed Community edition on your own machine.

## From conversation to next steps

- **Record or upload.** Capture your microphone, include meeting-tab audio where the browser supports it, or upload an existing recording.
- **Read the essentials.** Get a transcript, summary, key points, and action items with suggested owners and deadlines. Review generated notes before acting on them.
- **Ask your meeting.** Ask follow-up questions using the transcript as context.
- **Keep it organized.** Search transcripts, rename meetings, add tags and favorites, and filter your library.
- **Share or export.** Create a read-only share link, download audio or text, or save a PDF through the browser's print dialog.
- **Choose your AI setup.** Use your own API keys, or run transcription and note generation locally with faster-whisper and Ollama.

### A look inside

![A meeting summary in the Community edition](docs/launch/assets/community-summary.png)

<details>
<summary>Action items and meeting chat</summary>

![Action items in the Community edition](docs/launch/assets/community-actions.png)

![Meeting chat in the Community edition](docs/launch/assets/community-ask.png)

</details>

Screenshots show the Community UI with fictional meeting content and simulated AI responses. See [asset provenance](docs/launch/ASSETS.md).

## Online or self-hosted?

| | Hosted Minutes | Community edition in this repository |
|---|---|---|
| Start | [Open the app](https://minutes.manorai.xyz/) | Run Docker Compose |
| Account | Manor account | Local email and password |
| Transcripts, notes, actions, Ask | Included | Included |
| AI processing | Managed service, subject to account credits | Your API provider, or local models |
| Choose the output language for notes and actions | 43 choices | Hosted language selector not yet included |
| Create tasks inside Manor from Minutes | Available with Manor access | Hosted task integration not included |
| Manor MCP connection | Hosted integration | Cloud MCP server not included |
| Data storage | Managed by the hosted service | Your deployment |

Hosted Minutes and this repository ship separately. Browser support and model quality vary; installing Community does not include a Manor subscription or cloud credits. The self-hosted source is MIT licensed; hardware, hosting, and API usage may have their own costs.

## Self-host

These steps are for a development machine. You need Git, Docker, and Docker Compose v2.24 or newer. The supplied stack publishes database and storage ports and uses development defaults; see [deployment notes](docs/SELF_HOSTING.md#before-exposing-a-deployment) before putting it on a network.

```bash
git clone https://github.com/manor-os/minutes.git
cd minutes
cp .env.community.example .env
```

Edit `.env`: set a random `JWT_SECRET` and your own `ADMIN_EMAIL` / `ADMIN_PASSWORD`. API keys can be added in the app's Settings after sign-in; leave the optional server-wide keys unset if each user will bring their own.

```bash
docker compose -f docker-compose.yml -f docker-compose.community.yml up -d --build
```

Open **http://localhost:9002**, sign in with the admin credentials you set (or register a separate account), then add your transcription and language-model credentials in **Settings**. Record a short test or upload a file to check the complete flow.

### Use local models

Use this instead of the API-mode start command after preparing `.env`:

```bash
docker compose -f docker-compose.yml -f docker-compose.community.yml -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.community.yml -f docker-compose.local.yml exec ollama ollama pull qwen2.5:1.5b
```

The local overlay selects faster-whisper `base` and Ollama `qwen2.5:1.5b`. Initial image and model downloads require internet access. The Whisper model downloads on first use; give it time to finish before judging the first recording. AI inference then runs on your deployment without a paid model API. Speed, memory use, and note quality depend on your hardware and selected models.

[Setup, configuration, troubleshooting, and stopping services →](docs/SELF_HOSTING.md)

## Recording notes

- Microphone access requires `localhost` or HTTPS. Accessing the app from a phone over a plain HTTP LAN address may block recording.
- To include remote participants, share a supported browser tab and enable **Share audio**. System audio availability depends on browser and operating system.
- Live text arrives in chunks and can differ from the final transcript. Mobile/browser behavior can differ from the hosted app, which receives recorder fixes separately.
- Speaker separation is optional and requires additional setup; labels do not verify a person's identity. See [self-hosting](docs/SELF_HOSTING.md#speaker-labels).

## Built with

React / Vite · FastAPI · Celery / Redis · PostgreSQL · MinIO · faster-whisper / Ollama

```text
phone-recorder/          Web recorder, meeting library, actions, and chat
backend/api/            HTTP API, authentication, and AI services
backend/database/       Models and migrations
backend/celery_tasks.py  Background meeting processing
browser-extension/      Browser capture extension source
installer/              Installer source
docs/                   Setup documentation and launch assets
```

## Contributing

Bug reports, documentation improvements, and focused pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [roadmap](ROADMAP.md). Include your edition, browser, and deployment method when reporting a problem.

Minutes is part of [Manor AI](https://manorai.xyz/). The Community source is available under the [MIT license](LICENSE).
