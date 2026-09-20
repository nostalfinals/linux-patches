#!/usr/bin/env python3

import argparse
import hashlib
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

SOURCE_RPM = "libinput-1.31.3-1.fc44.src.rpm"
SOURCE_RPM_URL = (
    "https://kojipkgs.fedoraproject.org/packages/libinput/1.31.3/1.fc44/src/"
    + SOURCE_RPM
)
SOURCE_RPM_SHA256 = "e8b6690a66dd4f3d1f302528ee297dd67573fb708065aefd1abd5513d62c2c95"
RELEASE_SUFFIX = ".linuxpatches1"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def prepare_spec(spec_path: Path, patches: list[Path], sources_dir: Path) -> None:
    spec = spec_path.read_text()

    release_pattern = re.compile(r"^(Release:\s*.+)$", re.MULTILINE)
    release_match = release_pattern.search(spec)
    if not release_match:
        raise RuntimeError(f"Release field not found in {spec_path}")
    spec = release_pattern.sub(
        release_match.group(1) + RELEASE_SUFFIX,
        spec,
        count=1,
    )

    first_build_requirement = re.search(r"^BuildRequires:", spec, re.MULTILINE)
    if not first_build_requirement:
        raise RuntimeError(f"BuildRequires field not found in {spec_path}")

    patch_fields = []
    for number, patch in enumerate(patches, start=10000):
        shutil.copy2(patch, sources_dir / patch.name)
        patch_fields.append(f"Patch{number}:      {patch.name}")

    insertion = "\n".join(patch_fields) + "\n\n"
    offset = first_build_requirement.start()
    spec = spec[:offset] + insertion + spec[offset:]
    spec_path.write_text(spec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the patched libinput SRPM")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[2]
    patches = sorted((repository / "patches" / "libinput").glob("*.patch"))
    if not patches:
        raise RuntimeError("no libinput patches found")

    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="libinput-copr-") as temporary:
        topdir = Path(temporary) / "rpmbuild"
        for name in ("BUILD", "BUILDROOT", "RPMS", "SOURCES", "SPECS", "SRPMS"):
            (topdir / name).mkdir(parents=True)

        source_rpm = Path(temporary) / SOURCE_RPM
        urllib.request.urlretrieve(SOURCE_RPM_URL, source_rpm)
        digest = hashlib.sha256(source_rpm.read_bytes()).hexdigest()
        if digest != SOURCE_RPM_SHA256:
            raise RuntimeError(f"unexpected SHA-256 for {SOURCE_RPM}: {digest}")

        run(["rpm", "-i", "--define", f"_topdir {topdir}", str(source_rpm)])

        spec_path = topdir / "SPECS" / "libinput.spec"
        prepare_spec(spec_path, patches, topdir / "SOURCES")

        run(
            [
                "rpmbuild",
                "-bs",
                "--define",
                f"_topdir {topdir}",
                "--define",
                f"_srcrpmdir {outdir}",
                str(spec_path),
            ]
        )


if __name__ == "__main__":
    main()
