# secure-parental-app

## Local development

```bash
./dev.sh             # backend (in-memory, no AWS) on :8080 + parent web app on :3000
./dev.sh --desktop   # also launch the child GTK client, auto-registered to the local backend
./dev.sh --help      # all options
```

Parent auth is bypassed locally (any email/password logs in as `dev-parent-001`).
Per-service logs land in `.dev-logs/`. Ctrl+C stops everything.
