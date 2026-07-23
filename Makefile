SCHEMA_URL = https://api.lighton.ai/docs/schema/

.PHONY: test
test:  ## Run the test suite
	uv run pytest

.PHONY: release
release:  ## Cut a release: make release VERSION=0.2.0 [DESC="notes shown above the changelog"]
	@echo "$(VERSION)" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "VERSION must be semver, e.g. make release VERSION=0.2.0"; exit 1; }
	@[ -z "$$(git status --porcelain)" ] || { echo "working tree not clean — commit or stash first"; exit 1; }
	@[ "$$(git branch --show-current)" = "main" ] || { echo "release from main only"; exit 1; }
	@git rev-parse -q --verify "refs/tags/v$(VERSION)" >/dev/null && { echo "tag v$(VERSION) already exists"; exit 1; } || true
	uv version "$(VERSION)"   # updates pyproject.toml + uv.lock in one step
	git add pyproject.toml uv.lock
	git commit -m "chore(release): v$(VERSION)"
	@if [ -n "$(DESC)" ]; then git tag -a "v$(VERSION)" -m "$(DESC)"; else git tag "v$(VERSION)"; fi
	git push origin main "v$(VERSION)"

.PHONY: gen-types
gen-types:  ## Regenerate pydantic models from the LightOn OpenAPI schema
	mkdir -p lighton/types/api
	# Download first: --url leaves a trailing-slash mismatch in $$ref bases that breaks resolution.
	TMP=$$(mktemp) && \
	curl -fsSL $(SCHEMA_URL) -o $$TMP && \
	uv run datamodel-codegen \
		--input $$TMP \
		--input-file-type openapi \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.11 \
		--use-union-operator \
		--use-standard-collections \
		--use-schema-description \
		--use-annotated \
		--formatters ruff-check ruff-format \
		--custom-file-header "# Generated from the LightOn OpenAPI schema. Do not edit by hand — run 'make gen-types'." \
		--output lighton/types/api/__init__.py && \
	rm -f $$TMP
