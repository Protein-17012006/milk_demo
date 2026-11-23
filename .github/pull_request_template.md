## What and why

<!-- One or two sentences. Link the Confluence page or issue if there is one. -->

## Definition of done

- [ ] The four checks are green: lint, test, cfn-lint, image
- [ ] New behaviour has a test; hub coverage stays at 80% or more
- [ ] Settings or secrets added? Added to `infra/app.yml` (task definition) and described in README
- [ ] Changes `infra/platform.yml`? The change-set preview in the Infrastructure run looks right (no unexpected replacement)
- [ ] Changes the stored capture format? Old result files still re-index (`python -m milk.reindex --dry-run`)
- [ ] No keys, passwords, IP addresses, store images or model weights in the diff
- [ ] Docs updated (README, `docs/runbook.md`) if how to run or release changed

## After merge

The CD run deploys to development, test and staging by itself; production waits for approval.
