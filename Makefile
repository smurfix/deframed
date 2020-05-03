#!/usr/bin/make -f

.PHONY: doc test update all tag pypi upload

all: dirs\
	deframed/static/ext/msgpack.min.js  \
	deframed/static/ext/mustache.min.js \
	deframed/static/ext/jquery.min.js   \
	deframed/static/ext/poppler.min.js   \
	deframed/static/ext/bootstrap.min.js   \
	deframed/static/ext/bootstrap.min.css

dirs: deframed/static/ext
deframed/static/ext:
	mkdir $@
deframed/static/ext/msgpack.min.js:
	wget -O $@ "https://github.com/ygoe/msgpack.js/raw/master/msgpack.min.js"

deframed/static/ext/mustache.min.js:
	wget -O $@ "https://github.com/janl/mustache.js/raw/master/mustache.min.js"

deframed/static/ext/jquery.min.js:
	wget -O $@ "https://code.jquery.com/jquery-3.4.1.slim.min.js"

deframed/static/ext/poppler.min.js:
	wget -O $@ "https://cdn.jsdelivr.net/npm/popper.js@1.16.0/dist/umd/popper.min.js"

deframed/static/ext/bootstrap.min.js:
	wget -O $@ "https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/js/bootstrap.min.js"


#deframed/static/ext/cash.min.js:
#	wget -O $@ "https://github.com/fabiospampinato/cash/raw/master/dist/cash.min.js"

deframed/static/ext/bootstrap.min.css:
	wget -O $@ "https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/css/bootstrap.min.css"

# need to use python3 sphinx-build
PATH := /usr/share/sphinx/scripts/python3:${PATH}

PACKAGE = calltest
PYTHON ?= python3
export PYTHONPATH=$(shell pwd)

PYTEST ?= ${PYTHON} $(shell which pytest-3)
TEST_OPTIONS ?= -xvvv --full-trace
PYLINT_RC ?= .pylintrc

BUILD_DIR ?= build
INPUT_DIR ?= docs/source

# Sphinx options (are passed to build_docs, which passes them to sphinx-build)
#   -W       : turn warning into errors
#   -a       : write all files
#   -b html  : use html builder
#   -i [pat] : ignore pattern

SPHINXOPTS ?= -a -W -b html
AUTOSPHINXOPTS := -i *~ -i *.sw* -i Makefile*

SPHINXBUILDDIR ?= $(BUILD_DIR)/sphinx/html
ALLSPHINXOPTS ?= -d $(BUILD_DIR)/sphinx/doctrees $(SPHINXOPTS) docs

doc:
	sphinx3-build -a $(INPUT_DIR) $(BUILD_DIR)

livehtml: docs
	sphinx-autobuild $(AUTOSPHINXOPTS) $(ALLSPHINXOPTS) $(SPHINXBUILDDIR)

test:
	$(PYTEST) $(PACKAGE) $(TEST_OPTIONS)


tagged:
	git describe --tags --exact-match
	test $$(git ls-files -m | wc -l) = 0

pypi:   tagged
	python3 setup.py sdist upload

upload: pypi
	git push-all --tags

update:
	pip install -r ci/test-requirements.txt

