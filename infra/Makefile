ENV ?= dev
TF = terraform

.PHONY: fmt validate bootstrap init plan apply destroy output

fmt:
	$(TF) fmt -recursive

validate:
	$(TF) -chdir=envs/$(ENV) init -backend=false -input=false >/dev/null
	$(TF) -chdir=envs/$(ENV) validate

bootstrap:
	$(TF) -chdir=bootstrap init
	$(TF) -chdir=bootstrap apply

init:
	$(TF) -chdir=envs/$(ENV) init -backend-config="bucket=$$($(TF) -chdir=bootstrap output -raw state_bucket)"

plan:
	$(TF) -chdir=envs/$(ENV) plan

apply:
	$(TF) -chdir=envs/$(ENV) apply

destroy:
	$(TF) -chdir=envs/$(ENV) destroy

output:
	$(TF) -chdir=envs/$(ENV) output
