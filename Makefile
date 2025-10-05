.PHONY: dev-ec2 dev-local prod-deploy \
deploy\:new-green deploy\:canary-10 deploy\:canary-50 deploy\:flip \
deploy\:retire-blue deploy\:rollback

INSTALL_DOTFILES ?= false
GREEN_CAPACITY   ?= 2
GREEN_MIN_SIZE   ?= 1
GREEN_MAX_SIZE   ?= 3
BLUE_RETIRE_CAPACITY ?= 0
DRAIN_WAIT ?= 180

dev-ec2:
        terraform -chdir=terraform/dev init
        terraform -chdir=terraform/dev apply -auto-approve -var "install_dotfiles=$(INSTALL_DOTFILES)"

dev-local:
	terraform -chdir=terraform/local init
	terraform -chdir=terraform/local apply -auto-approve -var "install_dotfiles=$(INSTALL_DOTFILES)"

prod-deploy:
        terraform -chdir=terraform/prod init
        terraform -chdir=terraform/prod apply -auto-approve

deploy\:new-green:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "green_desired_capacity=$(GREEN_CAPACITY)" \
  -var "green_min_size=$(GREEN_MIN_SIZE)" \
  -var "green_max_size=$(GREEN_MAX_SIZE)" \
  -var "traffic_split=[]" \
  -var "active_color=blue"

deploy\:canary-10:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "traffic_split=[{tg=\"blue\",weight=90},{tg=\"green\",weight=10}]" \
  -var "active_color=blue"

deploy\:canary-50:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "traffic_split=[{tg=\"blue\",weight=50},{tg=\"green\",weight=50}]" \
  -var "active_color=blue"

deploy\:flip:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "traffic_split=[]" \
  -var "active_color=green"

deploy\:retire-blue:
	@echo "Waiting $(DRAIN_WAIT)s before retiring blue capacity..."
	sleep $(DRAIN_WAIT)
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "blue_desired_capacity=$(BLUE_RETIRE_CAPACITY)" \
  -var "blue_min_size=$(BLUE_RETIRE_CAPACITY)" \
  -var "traffic_split=[]" \
  -var "active_color=green"

deploy\:rollback:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var "traffic_split=[]" \
  -var "active_color=blue"
