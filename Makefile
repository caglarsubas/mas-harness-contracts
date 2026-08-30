.DEFAULT_GOAL := help

.PHONY: help prefetch zero-bill test typecheck build

help:
	@python3 ci/run_make_target.py help

prefetch:
	@python3 ci/run_make_target.py prefetch

zero-bill:
	@python3 ci/run_make_target.py zero-bill

test:
	@python3 ci/run_make_target.py test

typecheck:
	@python3 ci/run_make_target.py typecheck

build:
	@python3 ci/run_make_target.py build

%:
	@python3 ci/run_make_target.py "$@"

