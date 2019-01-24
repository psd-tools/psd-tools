BRANCH=master

clean:
	rm -rf dist/ build/

package:
	pip install wheel
	python setup.py sdist
	python setup.py bdist_wheel --universal

publish: package
	test -n "$(shell git branch | grep '* ${BRANCH}')"
	pip install twine
	twine upload dist/*

docs:
	make -C docs html

.PHONY: clean package publish docs
