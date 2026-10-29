# GitHub launch materials

Prepared for [manor-os/minutes](https://github.com/manor-os/minutes). The hosted app is the primary entry point; this repository provides the Community self-hosted source.

| Material | File |
|---|---|
| English repository homepage | [README](../../README.md) |
| Chinese repository homepage | [简体中文](../../README.zh-CN.md) |
| Installation and troubleshooting | [Self-hosting](../SELF_HOSTING.md) |
| Contributor setup | [Contributing](../../CONTRIBUTING.md) |
| Repository description and topics | [Copyable metadata](repository-metadata.json) |
| Announcement / release-body draft | [English and Chinese copy](announcement.md) |
| Social card and screenshots | [Asset index and provenance](ASSETS.md) |
| Local visual review | [Review page](index.html) |
| Verification scope | [Validation](VALIDATION.md) |

## Use

The README files and templates can merge as documentation. The announcement is a draft, not evidence that a release tag exists. Select a tested code revision and version before publishing a GitHub Release.

The About description/topics are proposed values. The social preview must be uploaded in repository Settings; committing its PNG does not update that setting.

The promotional trial, prices, and guaranteed recording hours are omitted. Publish promotional claims only after redemption, eligibility, and limits are working and verified. Hosted-only features are explicitly distinguished from the public source.

## Regenerate visuals

With frontend dependencies installed, build Community as in CONTRIBUTING.md. Then, from the repository root:

```bash
CHROMIUM_PATH=/path/to/chrome node docs/launch/source/capture-community.mjs
CHROMIUM_PATH=/path/to/chrome node docs/launch/source/render-social.mjs
```

The capture uses fictional API fixtures and blocks nonlocal requests. It is a UI demonstration, not an AI-quality or clean-install test.
