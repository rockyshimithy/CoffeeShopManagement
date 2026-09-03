SHELL=/bin/bash

help:
	@echo 'Makefile for EmployeeManagement                               '
	@echo '                                                              '
	@echo 'Usage:                                                        '
	@echo '    make clean              Remove python compiled files      '
# 	@echo '    make requirements       Install required packages         '
# 	@echo '    make requirements_dev   Install required packages to Dev  '
# 	@echo '    make unit               Run unit tests                    '
# 	@echo '    make superuser          Create admin user on Django       '
# 	@echo '    make migrate_db         Apply the migrations to db        '
# 	@echo '    make runserver          Run the application               '
	@echo '                                                              '


.PHONY: clean clean-pyc

clean-pyc:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete

clean: clean-pyc
	rm -rf .cache .pytest_cache .ruff_cache .coverage htmlcov staticfiles












# requirements:
# 	pip install -r requirements.txt

# requirements_dev:
# 	pip install -r requirements_dev.txt


# unit:clean
# 	py.test tests/ -v


# superuser:
# 	python manage.py createsuperuser

# migrate_db:
# 	python manage.py migrate

# runserver:
# 	python manage.py runserver

