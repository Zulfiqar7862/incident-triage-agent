# AI interaction log

This project was built with an AI assistant (Claude), as the assignment requires.

Put the complete, unedited transcript of that conversation here, from planning
through implementation and review. Export it from the chat interface and paste
it below, or link to a shared copy.

The git history shows how the solution evolved, including the bugs the build
surfaced and their fixes:

- the log generator cycled through a single template (`(i * 7) % 7 == 0`)
- task-launching endpoints ran in FastAPI's threadpool, where there is no event loop
- visual review in headless Chromium found mobile layout, dark-mode contrast and
  stale run-list status issues

---

<!-- paste transcript below -->
