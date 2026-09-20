#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PatchctlError(Exception):
    pass


def run(command, *, cwd=None, capture=False, check=True):
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def load_project(name):
    path = ROOT / "projects.toml"
    if not path.is_file():
        raise PatchctlError(f"missing project config: {path}")

    with path.open("rb") as config_file:
        projects = tomllib.load(config_file)

    try:
        config = projects[name]
    except KeyError:
        raise PatchctlError(f"unknown project: {name}") from None

    required = ("upstream_url", "upstream_branch", "upstream_commit")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise PatchctlError(f"missing {', '.join(missing)} in {path}")

    return config


def project_paths(name):
    return ROOT / "work" / name, ROOT / "patches" / name


def git(source_dir, *arguments, **kwargs):
    return run(["git", *arguments], cwd=source_dir, **kwargs)


def is_ancestor(source_dir, ancestor, descendant):
    result = git(
        source_dir,
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
        check=False,
    )
    return result.returncode == 0


def prepare(name, config):
    source_dir, patch_dir = project_paths(name)
    if source_dir.exists():
        raise PatchctlError(
            f"{source_dir} already exists; remove it before preparing again"
        )
    if not patch_dir.is_dir():
        raise PatchctlError(f"missing patch directory: {patch_dir}")

    source_dir.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--branch",
            config["upstream_branch"],
            config["upstream_url"],
            str(source_dir),
        ]
    )

    remote_branch = f"origin/{config['upstream_branch']}"
    upstream_commit = config["upstream_commit"]
    if not is_ancestor(source_dir, upstream_commit, remote_branch):
        raise PatchctlError(
            f"{upstream_commit} is not on upstream branch "
            f"{config['upstream_branch']}"
        )

    git(source_dir, "reset", "--hard", upstream_commit)

    patches = sorted(patch_dir.glob("*.patch"))
    if patches:
        git(source_dir, "am", *(str(patch) for patch in patches))

    print(f"prepared {name} at {source_dir}")


def rebuild(name, config):
    source_dir, patch_dir = project_paths(name)
    if not (source_dir / ".git").exists():
        raise PatchctlError(
            f"{source_dir} is not prepared; run ./patchctl.py prepare {name} first"
        )

    status = git(source_dir, "status", "--porcelain", capture=True).stdout
    if status:
        raise PatchctlError(f"{source_dir} has uncommitted changes")

    upstream_commit = config["upstream_commit"]
    if not is_ancestor(source_dir, upstream_commit, "HEAD"):
        raise PatchctlError(f"{upstream_commit} is not an ancestor of HEAD")

    merges = git(
        source_dir,
        "rev-list",
        "--merges",
        f"{upstream_commit}..HEAD",
        capture=True,
    ).stdout
    if merges:
        raise PatchctlError("cannot rebuild patches from history containing merges")

    with tempfile.TemporaryDirectory(prefix=".rebuild.", dir=patch_dir) as temp:
        temp_dir = Path(temp)
        git(
            source_dir,
            "format-patch",
            "--diff-algorithm=myers",
            "--zero-commit",
            "--full-index",
            "--no-signature",
            "--no-stat",
            "-N",
            "--output-directory",
            str(temp_dir),
            f"{upstream_commit}..HEAD",
            capture=True,
        )
        new_patches = sorted(temp_dir.glob("*.patch"))

        for patch in patch_dir.glob("*.patch"):
            patch.unlink()
        for patch in new_patches:
            shutil.move(patch, patch_dir / patch.name)

    print(f"rebuilt {len(new_patches)} patch(es) in {patch_dir}")


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "rebuild"):
        command = subparsers.add_parser(action)
        command.add_argument("project")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_project(args.project)
    actions = {
        "prepare": prepare,
        "rebuild": rebuild,
    }
    actions[args.action](args.project, config)


if __name__ == "__main__":
    try:
        main()
    except PatchctlError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as error:
        print(f"command not found: {error.filename}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
