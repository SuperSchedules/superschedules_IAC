.PHONY: dev-ec2 dev-local prod-deploy \
deploy\:new-green deploy\:new-blue deploy\:canary-10 deploy\:canary-50 deploy\:flip \
deploy\:retire-blue deploy\:rollback deploy\:safe \
deploy\:scale-down-blue deploy\:scale-down-green

INSTALL_DOTFILES ?= false
GREEN_CAPACITY   ?= 1
GREEN_MIN_SIZE   ?= 1
GREEN_MAX_SIZE   ?= 2
BLUE_CAPACITY    ?= 1
BLUE_MIN_SIZE    ?= 1
BLUE_MAX_SIZE    ?= 2
BLUE_RETIRE_CAPACITY ?= 0
ACTIVE_DESIRED_CAPACITY ?= 1
ACTIVE_MIN_SIZE ?= 1
ACTIVE_MAX_SIZE ?= 2
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
	@echo "Checking current active color..."
	@CURRENT_ACTIVE=$$(terraform -chdir=terraform/prod output -raw active_color 2>/dev/null || echo "unknown"); \
	if [ "$$CURRENT_ACTIVE" = "green" ]; then \
		echo "⚠️  WARNING: Green is currently ACTIVE (serving production traffic)!"; \
		echo "⚠️  Deploying to green will disrupt live service."; \
		echo "⚠️  You should deploy to blue instead, or run deploy:rollback first."; \
		echo ""; \
		read -p "Continue anyway? (yes/NO): " confirm; \
		if [ "$$confirm" != "yes" ]; then \
			echo "Deployment cancelled."; \
			exit 1; \
		fi; \
	else \
		echo "✓ Blue is active, deploying to green is safe."; \
	fi
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "green_desired_capacity=$(GREEN_CAPACITY)" \
  -var "green_min_size=$(GREEN_MIN_SIZE)" \
  -var "green_max_size=$(GREEN_MAX_SIZE)" \
  -var "blue_desired_capacity=$(ACTIVE_DESIRED_CAPACITY)" \
  -var "blue_min_size=$(ACTIVE_MIN_SIZE)" \
  -var "blue_max_size=$(ACTIVE_MAX_SIZE)" \
  -var "traffic_split=[]" \
  -var "active_color=blue"

deploy\:new-blue:
	@echo "Checking current active color..."
	@CURRENT_ACTIVE=$$(terraform -chdir=terraform/prod output -raw active_color 2>/dev/null || echo "unknown"); \
	if [ "$$CURRENT_ACTIVE" = "blue" ]; then \
		echo "⚠️  WARNING: Blue is currently ACTIVE (serving production traffic)!"; \
		echo "⚠️  Deploying to blue will disrupt live service."; \
		echo "⚠️  You should deploy to green instead, or run deploy:flip first."; \
		echo ""; \
		read -p "Continue anyway? (yes/NO): " confirm; \
		if [ "$$confirm" != "yes" ]; then \
			echo "Deployment cancelled."; \
			exit 1; \
		fi; \
	else \
		echo "✓ Green is active, deploying to blue is safe."; \
	fi
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "blue_desired_capacity=$(BLUE_CAPACITY)" \
  -var "blue_min_size=$(BLUE_MIN_SIZE)" \
  -var "blue_max_size=$(BLUE_MAX_SIZE)" \
  -var "green_desired_capacity=$(ACTIVE_DESIRED_CAPACITY)" \
  -var "green_min_size=$(ACTIVE_MIN_SIZE)" \
  -var "green_max_size=$(ACTIVE_MAX_SIZE)" \
  -var "traffic_split=[]" \
  -var "active_color=green"

deploy\:canary-10:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "green_desired_capacity=$(GREEN_CAPACITY)" \
  -var "green_min_size=$(GREEN_MIN_SIZE)" \
  -var "green_max_size=$(GREEN_MAX_SIZE)" \
  -var "traffic_split=[{tg=\"blue\",weight=90},{tg=\"green\",weight=10}]" \
  -var "active_color=blue"

deploy\:canary-50:
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "green_desired_capacity=$(GREEN_CAPACITY)" \
  -var "green_min_size=$(GREEN_MIN_SIZE)" \
  -var "green_max_size=$(GREEN_MAX_SIZE)" \
  -var "traffic_split=[{tg=\"blue\",weight=50},{tg=\"green\",weight=50}]" \
  -var "active_color=blue"

deploy\:flip:
	@echo "WARNING: This will switch production traffic to GREEN!"
	@read -p "Are you sure you want to flip traffic to GREEN? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ]; then \
		echo "Flip cancelled."; \
		exit 1; \
	fi
	@echo "Running: make deploy:flip"
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "blue_desired_capacity=$(BLUE_RETIRE_CAPACITY)" \
  -var "blue_min_size=$(BLUE_RETIRE_CAPACITY)" \
  -var "blue_max_size=2" \
  -var "green_desired_capacity=$(GREEN_CAPACITY)" \
  -var "green_min_size=$(GREEN_MIN_SIZE)" \
  -var "green_max_size=$(GREEN_MAX_SIZE)" \
  -var "traffic_split=[]" \
  -var "active_color=green"

deploy\:retire-blue:
	@echo "Waiting $(DRAIN_WAIT)s before retiring blue capacity..."
	sleep $(DRAIN_WAIT)
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "blue_desired_capacity=$(BLUE_RETIRE_CAPACITY)" \
  -var "blue_min_size=$(BLUE_RETIRE_CAPACITY)" \
  -var "traffic_split=[]" \
  -var "active_color=green"

deploy\:rollback:
	@echo "WARNING: This will rollback production traffic to BLUE!"
	@read -p "Are you sure you want to rollback to BLUE? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ]; then \
		echo "Rollback cancelled."; \
		exit 1; \
	fi
	@echo "Running: make deploy:rollback"
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
  -var-file=terraform.tfvars \
  -var "blue_desired_capacity=$(GREEN_CAPACITY)" \
  -var "blue_min_size=$(GREEN_MIN_SIZE)" \
  -var "blue_max_size=$(GREEN_MAX_SIZE)" \
  -var "green_desired_capacity=0" \
  -var "green_min_size=0" \
  -var "traffic_split=[]" \
  -var "active_color=blue"

deploy\:safe:
	@echo "Detecting current active color and deploying to inactive one..."
	@terraform -chdir=terraform/prod init >/dev/null 2>&1
	@CURRENT_ACTIVE=$$(terraform -chdir=terraform/prod output -raw active_color 2>/dev/null || echo "blue"); \
	if [ "$$CURRENT_ACTIVE" = "blue" ]; then \
		echo "✓ Blue is active, deploying to green"; \
		$(MAKE) deploy:new-green; \
	else \
		echo "✓ Green is active, deploying to blue"; \
		echo "⚠️  Note: No deploy:new-blue target exists yet. Creating blue deployment..."; \
		terraform -chdir=terraform/prod apply -auto-approve \
			-var-file=terraform.tfvars \
			-var "blue_desired_capacity=$(GREEN_CAPACITY)" \
			-var "blue_min_size=$(GREEN_MIN_SIZE)" \
			-var "blue_max_size=$(GREEN_MAX_SIZE)" \
			-var "traffic_split=[]" \
			-var "active_color=green"; \
	fi

deploy\:scale-down-blue:
	@echo "Scaling down blue environment to 0 instances..."
	@ACTIVE_COLOR=$$(terraform -chdir=terraform/prod output -raw active_color 2>/dev/null || echo "unknown"); \
	if [ "$$ACTIVE_COLOR" = "blue" ]; then \
		echo "⚠️  ERROR: Blue is currently ACTIVE! Cannot scale down the active environment."; \
		exit 1; \
	fi
	@echo "Preserving green's current capacity (ACTIVE_DESIRED_CAPACITY=$(ACTIVE_DESIRED_CAPACITY))"
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
		-var-file=terraform.tfvars \
		-var "blue_desired_capacity=0" \
		-var "blue_min_size=0" \
		-var "blue_max_size=2" \
		-var "green_desired_capacity=$(ACTIVE_DESIRED_CAPACITY)" \
		-var "green_min_size=$(ACTIVE_MIN_SIZE)" \
		-var "green_max_size=$(ACTIVE_MAX_SIZE)" \
		-var "active_color=green"

deploy\:scale-down-green:
	@echo "Scaling down green environment to 0 instances..."
	@ACTIVE_COLOR=$$(terraform -chdir=terraform/prod output -raw active_color 2>/dev/null || echo "unknown"); \
	if [ "$$ACTIVE_COLOR" = "green" ]; then \
		echo "⚠️  ERROR: Green is currently ACTIVE! Cannot scale down the active environment."; \
		exit 1; \
	fi
	@echo "Preserving blue's current capacity (ACTIVE_DESIRED_CAPACITY=$(ACTIVE_DESIRED_CAPACITY))"
	terraform -chdir=terraform/prod init
	terraform -chdir=terraform/prod apply -auto-approve \
		-var-file=terraform.tfvars \
		-var "green_desired_capacity=0" \
		-var "green_min_size=0" \
		-var "green_max_size=2" \
		-var "blue_desired_capacity=$(ACTIVE_DESIRED_CAPACITY)" \
		-var "blue_min_size=$(ACTIVE_MIN_SIZE)" \
		-var "blue_max_size=$(ACTIVE_MAX_SIZE)" \
		-var "active_color=blue"
