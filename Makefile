BRANCH=master
VERSIONS=2.7 3.4 3.5 3.6

clean:
	rm -rf dist/ build/

package:
	pip install wheel
	python setup.py sdist
	for v in ${VERSIONS}; do python$$v setup.py bdist_wheel; done

publish: package
	test -n "$(shell git branch | grep '* ${BRANCH}')"
	pip install twine
	twine upload dist/*

docs:
	make -C docs html

.PHONY: clean package publish docs
