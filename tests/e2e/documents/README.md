# e2e documents

Drop the documents the end-to-end run should ingest here — every file with an
extension in this directory is picked up (`--docs <dir>` points elsewhere).

- The first document (alphabetically) is the one used by the single-file steps:
  `upload`, `tags`, `content_types`, `parse`, `extract`.
- All of them are uploaded by the `batch` step (twice: once sync, once async).
- Keep them small and non-confidential: they are uploaded to the live API, and
  whatever lands here is committed to the repo.
- `--ask-query` / `--search-query` should say something these documents can
  actually answer; the defaults are deliberately generic.

Everything the run creates lives in a throwaway `e2e-<timestamp>` workspace that
is deleted afterwards (`--keep` to keep it).
