SCHEMA_URL = https://api.lighton.ai/docs/schema/

.PHONY: test
test:  ## Run the test suite
	uv run pytest

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
