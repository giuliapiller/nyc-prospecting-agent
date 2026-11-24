.PHONY: install refresh test

install:
	python -m pip install -r requirements.txt

# Weekly refresh: all phases, then output/phase3_ranked.csv and output/dashboard.html. Needs GITHUB_TOKEN.
refresh:
	python -m prospecting run

test:
	python -m pytest -q
