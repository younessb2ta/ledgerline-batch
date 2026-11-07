ENV ?= dev
TF = terraform

.PHONY: fmt validate init plan apply destroy output bootstrap bootstrap-init

fmt:
	$(TF) fmt -recursive

validate:
	$(TF) -chdir=envs/$(ENV) init -backend=false -input=false >/dev/null
	$(TF) -chdir=envs/$(ENV) validate
	$(TF) -chdir=bootstrap init -backend=false -input=false >/dev/null
	$(TF) -chdir=bootstrap validate

# Free path: local state, no bootstrap required.
init:
	$(TF) -chdir=envs/$(ENV) init -input=false

plan:
	$(TF) -chdir=envs/$(ENV) plan

apply:
	$(TF) -chdir=envs/$(ENV) apply

destroy:
	$(TF) -chdir=envs/$(ENV) destroy

output:
	$(TF) -chdir=envs/$(ENV) output

# Paid path only: creates the GCS state bucket (needs billing).
bootstrap:
	$(TF) -chdir=bootstrap init
	$(TF) -chdir=bootstrap apply

bootstrap-init:
	$(TF) -chdir=bootstrap init -backend=false -input=false
