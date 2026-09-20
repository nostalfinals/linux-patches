.PHONY: srpm
srpm:
	dnf install -y ca-certificates python3 rpm-build
	python3 ./build-srpm.py --outdir "$(outdir)"
