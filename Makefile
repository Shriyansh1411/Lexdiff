PY ?= python3
REG_OLD = data/regulation/ftc_safeguards_2021-01-01.txt
REG_NEW = data/regulation/ftc_safeguards_2026-09-01.txt

.PHONY: install test demo guard guard-base benchmark dashboard demo-git clean

install:
	$(PY) -m pip install -r requirements.txt

test:            ## engine test-suite (pytest if installed, else unittest)
	@$(PY) -m pytest -q tests 2>/dev/null || $(PY) -m unittest discover -s tests -t . -q

demo:            ## all nine stages on the bundled Lendwise demo
	$(PY) -m lexdiff run --base demo/lendwise_base --head demo/lendwise_fixed \
	  --reg-old $(REG_OLD) --reg-new $(REG_NEW) --approver "Compliance Lead"

guard:           ## the zero-LLM CI gate on the fixed app (exit 0)
	$(PY) -m lexdiff guard --target demo/lendwise_fixed

guard-base:      ## the same gate on the base app (exit 1, one finding per violation)
	-$(PY) -m lexdiff guard --target demo/lendwise_base

benchmark:
	$(PY) -m lexdiff benchmark --target demo/lendwise_base

dashboard:
	$(PY) -m lexdiff dashboard

demo-git:        ## same proof, but base/head come from git refs
	bash scripts/init_demo_git.sh
	$(PY) -m lexdiff verify --base .demo_repo@main --head .demo_repo@lexdiff/ftc-safeguards-fix

clean:
	rm -rf .lexdiff .demo_repo compliance/obligations compliance/tests compliance/tests.lock.json
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
