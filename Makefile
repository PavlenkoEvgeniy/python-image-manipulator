.PHONY: help test install-dev run pyinstaller clean

help:
	@echo "Available targets:"
	@echo "  make test         - Run tests"
	@echo "  make install-dev  - Install in development mode with test dependencies"
	@echo "  make run          - Run the application from source"
	@echo "  make pyinstaller  - Build a standalone executable"
	@echo "  make clean        - Clean build artifacts"

test:
	python -m pytest -v

install-dev:
	pip install -e ".[dev]"

run:
	PYTHONPATH=src python main.py

pyinstaller:
	@case "$$(uname -s)" in \
		Darwin) icon=assets/icon.icns ;; \
		MINGW*|MSYS*|CYGWIN*) icon=assets/icon.ico ;; \
		*) icon=assets/icon.png ;; \
	esac; \
	PYTHONPATH=src pyinstaller --onefile --windowed \
		--icon=$$icon \
		--collect-data=image_manipulator \
		--hidden-import=PIL._tkinter_finder \
		--hidden-import=PIL._imagingtk \
		--hidden-import=tkinterdnd2 \
		--name ImageManipulator main.py

clean:
	rm -rf build dist *.spec __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
