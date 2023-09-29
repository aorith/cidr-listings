SHELL := bash

DB_IMAGE ?= postgres:15
DB_USERNAME ?= test
DB_PASSWORD ?= test1234
DB_HOST ?= 127.0.0.1
DB_PORT ?= 5432
DB_NAME ?= cidr

JWT_SECRET ?= super_secure_test_secret_!
TEST_USER ?= test
TEST_USER_PASSWORD ?= Ilovet3st!

# Don't load the variables early with ':=' here
LOAD_VENV = [[ -n "$$VIRTUAL_ENV" ]] || source .venv/bin/activate

# Create .venv
.venv:
	[[ -e .venv/bin/activate ]] || \
		python3 -m venv .venv && \
		source .venv/bin/activate && \
		pip install --upgrade pip && \
		pip install pip-tools

# Install requirements
.PHONY: install
install: .venv
	@$(LOAD_VENV) && \
		pip install --no-deps -r ./requirements/requirements.txt && \
		pip install --no-deps -r ./requirements/requirements-dev.txt

# Upgrade requirements
.PHONY: upgrade
upgrade: .venv
	@$(LOAD_VENV) && \
		mkdir -p requirements && \
		pip-compile --upgrade --strip-extras -o requirements/requirements.txt pyproject.toml && \
		pip-compile --upgrade --strip-extras --extra dev -o requirements/requirements-dev.txt pyproject.toml

# Run pytest tests
.PHONY: test
test: .venv
	@$(LOAD_VENV) && \
		make reset_app && \
		echo "Running tests ..." && \
		export JWT_SECRET=$(JWT_SECRET) && \
		pytest --show-capture=all --verbosity=10

# Teardown test DB
.PHONY: db_teardown
db_teardown:
	@docker stop test_postgres || true

# Start test DB
.PHONY: db_start
db_start:
	@docker run --rm --detach --name test_postgres \
		-p $(DB_PORT):5432 \
		-e POSTGRES_USER=$(DB_USERNAME) \
		-e POSTGRES_PASSWORD=$(DB_PASSWORD) \
		-e POSTGRES_DB=$(DB_NAME) \
		$(DB_IMAGE)

# Reset test DB
.PHONY: db_reset
db_reset:
	make db_teardown
	make db_start
	@sleep 1

# Reset app with migrations & test user
.PHONY: reset_app
reset_app:
	echo "Resetting the db ..."
	make db_reset
	@sleep 6
	@$(LOAD_VENV) && \
		echo "Running migrations and creating test superuser ..." && \
		cd src && \
		export JWT_SECRET=$(JWT_SECRET) && \
		litestar run-db-migrations && \
		litestar create-user --login $(TEST_USER) --password $(TEST_USER_PASSWORD) --superuser && \
		cd ..
