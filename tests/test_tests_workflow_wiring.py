"""Wiring checks for the workflow that runs this repository's test suite.

The workflow is parsed as YAML, so each assertion is scoped to the key it is
about: a string that survives only in a comment or in the wrong step cannot
satisfy it.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/tests.yml")
TIMEOUT_MINUTES = 15
CONCURRENCY_GROUP = (
    "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
)
CHECKSUM_COMMAND = 'echo "${VALE_SHA256}  ${archive}" | sha256sum -c -'


# Functional syntax, because `with` is a keyword and `cancel-in-progress` and
# `timeout-minutes` are not valid identifiers.
_Step = typ.TypedDict(
    "_Step",
    {
        "name": str,
        "uses": str,
        "run": str,
        "env": dict[str, str],
        "with": dict[str, object],
    },
    total=False,
)
_Concurrency = typ.TypedDict("_Concurrency", {"group": str, "cancel-in-progress": str})
_Job = typ.TypedDict("_Job", {"timeout-minutes": int, "steps": list[_Step]})


class _Workflow(typ.TypedDict, total=False):
    """The top-level workflow keys these tests read.

    YAML 1.1 reads the bare key `on` as the boolean True, so the triggers are
    reached through `_triggers` rather than a field here.
    """

    permissions: dict[str, str]
    concurrency: _Concurrency
    jobs: dict[str, _Job]


def _workflow() -> _Workflow:
    """Return the parsed workflow."""
    return typ.cast("_Workflow", yaml.safe_load(WORKFLOW.read_text()))


def _triggers() -> dict[str, object]:
    """Return the `on:` mapping; YAML 1.1 reads the bare key `on` as True."""
    workflow = typ.cast("dict[str | bool, dict[str, object]]", _workflow())
    return workflow["on"] if "on" in workflow else workflow[True]


def _job() -> _Job:
    """Return the single job that runs the suite."""
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["tests"], f"expected one `tests` job, found {list(jobs)}"
    return jobs["tests"]


def _steps() -> list[_Step]:
    """Return the job's steps in order."""
    return _job()["steps"]


def _step(name: str) -> tuple[int, _Step]:
    """Return the index and body of the step called `name`."""
    for index, step in enumerate(_steps()):
        if step.get("name") == name:
            return index, step
    message = f"no step named {name!r}"
    raise AssertionError(message)


def test_the_suite_runs_on_pushes_to_main_and_on_pull_requests() -> None:
    """Both triggers must be present, and the push trigger limited to main.

    Dropping `pull_request` would stop the suite gating changes before merge;
    dropping the `main` push would stop it covering what lands.
    """
    triggers = _triggers()

    assert "pull_request" in triggers, "the suite must run on pull requests"
    assert triggers["push"] == {"branches": ["main"]}, "push must be limited to main"


def test_the_suite_is_run_through_make_test_as_the_last_step() -> None:
    """CI must run the suite with the Makefile's own entry point, after setup.

    A step that only mentions pytest, or a different target, would let the
    workflow stay green while the suite the developers run goes unrun.
    """
    steps = _steps()

    assert steps[-1].get("run") == "make test", "the last step must run `make test`"


def test_vale_is_pinned_and_verified_by_checksum() -> None:
    """The Vale step must pin a release and check its digest before unpacking.

    The style tests exercise a real Vale, so an unpinned download would let an
    upstream release change what passes. The `sha256sum -c` command is what turns
    a mismatch into a failure, so it is asserted as a command in this step's own
    script, ahead of the unpack, not as a name that could sit anywhere.
    """
    _, step = _step("Install Vale")
    env = step["env"]
    script = step["run"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", env["VALE_VERSION"]), "pin a Vale release"
    assert re.fullmatch(r"[0-9a-f]{64}", env["VALE_SHA256"]), "pin a SHA-256 digest"
    assert CHECKSUM_COMMAND in script, "the download must be checked by checksum"
    assert script.index(CHECKSUM_COMMAND) < script.index("tar -xzf"), (
        "the checksum must be verified before the archive is unpacked"
    )
    assert 'echo "${vale_dir}" >> "${GITHUB_PATH}"' in script, (
        "the verified binary must be put on PATH for later steps"
    )


def test_vale_is_installed_before_the_tests_run() -> None:
    """The install step must precede `make test`, or the harness finds no Vale."""
    install, _ = _step("Install Vale")
    run, _ = _step("Run the tests")

    assert install < run, "Vale must be installed before the tests run"


def test_the_job_has_a_timeout_and_read_only_permissions() -> None:
    """The job needs a ceiling, and the token needs no more than read access."""
    workflow = _workflow()

    assert isinstance(_job()["timeout-minutes"], int), "the job needs a timeout"
    assert workflow["permissions"] == {"contents": "read"}, "keep the token read-only"


def test_the_job_timeout_is_fifteen_minutes() -> None:
    """The ceiling is the documented 15 minutes, so removing or raising it fails."""
    assert _job()["timeout-minutes"] == TIMEOUT_MINUTES, "keep the 15 minute ceiling"


def test_superseded_pull_request_runs_are_cancelled_and_pushes_are_not() -> None:
    """Concurrency groups runs per pull request and cancels only pull-request runs.

    Cancelling a push run would leave `main` without a result for its commit.
    """
    concurrency = _workflow()["concurrency"]

    assert concurrency["group"] == CONCURRENCY_GROUP, (
        "pull-request runs must share a group per number; push runs a group each"
    )
    assert concurrency["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    ), "only pull-request runs may be cancelled"


def test_checkout_does_not_persist_credentials() -> None:
    """The checkout must not leave the token in the git config for later steps."""
    _, step = _step("Check out repository")

    assert step["uses"].startswith("actions/checkout@"), "expected the checkout action"
    assert step["with"]["persist-credentials"] is False, "drop persisted credentials"


def test_every_action_is_pinned_to_a_commit() -> None:
    """Every `uses:` must name a full commit, so a moved tag cannot change CI."""
    uses = [step["uses"] for step in _steps() if "uses" in step]

    assert uses, "the workflow should use at least the checkout action"
    for use in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", use), f"unpinned action: {use}"
