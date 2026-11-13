# Publishing and commit guidelines

This repository is delivered in three feature batches, with at least four hours between successful pushes. The four-hour instruction replaces the earlier two-hour plan.

| Batch | Earliest delivery | Scope |
| --- | --- | --- |
| 1 | First successful push | SQLite verification backend, fake providers, idempotency, billing, recovery tests and backend setup |
| 2 | Four hours after batch 1 | React verification page, validation, retry handling, masked history, accessibility and frontend tests |
| 3 | Four hours after batch 2 | Docker replicas, Nginx gateway, Make targets, CI, operating guide and complete acceptance documentation |

The implementation was completed and tested locally before these delivery batches were prepared. The previous local Git metadata was unavailable when publishing began, so these are new commits organized from the existing source. Their creation times are genuine; the publishing intervals do not imply additional development happened between pushes.

## Commit guidelines

- Keep each commit focused on a reviewable feature or deployment concern.
- Use a descriptive title with a scope, such as `feat(backend): add SQLite PAN verification and recovery`.
- Include the relevant tests with the feature they verify.
- Keep secrets, database files, generated dependencies, caches and local tools out of Git.
- Preserve actual commit dates and authorship. Do not backdate commits or force-push a replacement history.
- Publish only the frozen commit selected for each batch, rather than pushing all branches or tags.

## Timed delivery

The local publisher records each successful remote update and waits at least four hours before the next one. It checks that the remote branch still matches the last published commit and stops if somebody else changes that branch. It never uses a force push.

Future delivery requires this Windows computer to be awake, the scheduled user's session to be logged in, internet access and working Git credentials. A missed run is handled when the task can run again; the next four-hour interval starts from that successful push, so delayed batches are not sent together.

The local schedule, frozen commit IDs and execution log are kept under the ignored `.tools/publishing` directory. The publisher disables its own scheduled task after the third batch.
