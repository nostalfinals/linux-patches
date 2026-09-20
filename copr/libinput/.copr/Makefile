SCRIPT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

.PHONY: srpm
srpm:
	dnf install -y ca-certificates python3 rpm-build
	python3 "$(SCRIPT_DIR)/build-srpm.py" --outdir "$(outdir)"
