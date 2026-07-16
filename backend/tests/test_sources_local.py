"""Adapters that read the machine: git branches, todo lines, markdown docs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.sources.git import GitSource
from app.sources.keys import all_reference_keys, github_keys, linear_keys
from app.sources.markdown import MarkdownSource
from app.sources.todos import TodoSource


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "widgets"
    path.mkdir()
    run = lambda *args: subprocess.run(args, cwd=path, check=True, capture_output=True)  # noqa: E731
    # -b pins the default branch: it otherwise depends on the developer's git config.
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "T")
    (path / "f.txt").write_text("hi")
    run("git", "add", "f.txt")
    run("git", "commit", "-qm", "init")
    run("git", "checkout", "-q", "-b", "someone/eng-42-search-timeout")
    return path


class TestKeys:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Closes ENG-42", {"ENG-42"}),
            ("ENG-42 and OPS-7 both", {"ENG-42", "OPS-7"}),
            ("no keys here", set()),
            ("A-1 is too short a prefix", set()),
            ("lowercase eng-42 is not a key", set()),
        ],
    )
    def test_linear_keys(self, text, expected):
        assert linear_keys(text) == expected

    def test_github_url_becomes_a_key(self):
        assert github_keys("see https://github.com/acme/widgets/pull/1201") == {"gh:acme/widgets#1201"}

    def test_shorthand_needs_a_repo_to_resolve_against(self):
        assert github_keys("see #1201") == set()
        assert github_keys("see #1201", default_repo="acme/widgets") == {"gh:acme/widgets#1201"}

    def test_all_reference_keys_combines_both_kinds(self):
        keys = all_reference_keys("ENG-42 fixed by https://github.com/acme/widgets/pull/7")
        assert keys == {"ENG-42", "gh:acme/widgets#7"}


class TestGit:
    async def test_reads_branches(self, repo):
        source = GitSource({"repos": str(repo)})

        items = await source.fetch()

        labels = {item.label for item in items}
        assert labels == {"[widgets] someone/eng-42-search-timeout", "[widgets] main"}
        assert all(item.source == "branch" for item in items)

    async def test_a_branch_name_references_its_ticket(self, repo):
        items = await GitSource({"repos": str(repo)}).fetch()

        branch = next(i for i in items if "eng-42" in i.label)
        assert "ENG-42" in branch.reference_keys, "this is how a branch finds its issue"

    async def test_branch_ids_are_url_safe(self, repo):
        items = await GitSource({"repos": str(repo)}).fetch()
        assert all("/" not in item.id for item in items)

    async def test_old_branches_are_skipped_unless_they_carry_your_prefix(self, repo):
        source = GitSource({"repos": str(repo), "branch_prefix": "someone/", "max_age_days": "0"})

        labels = {item.label for item in await source.fetch()}

        assert labels == {"[widgets] someone/eng-42-search-timeout"}

    async def test_a_broken_repo_does_not_fail_the_others(self, repo, tmp_path):
        source = GitSource({"repos": f"{tmp_path / 'not-a-repo'},{repo}"})
        assert len(await source.fetch()) == 2

    async def test_check_rejects_a_path_that_is_not_a_repo(self, tmp_path):
        from app.sources.base import SourceNotConfigured

        with pytest.raises(SourceNotConfigured):
            await GitSource({"repos": str(tmp_path)}).check()

    async def test_unconfigured_fetches_nothing(self):
        assert await GitSource({}).fetch() == []


class TestTodos:
    @pytest.fixture
    def todo_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "todo.md"
        path.write_text(
            "# My todos\n"
            "- [ ] Write tests for the retry path\n"
            "- [x] Already done, ignore me\n"
            "TODO: Chase the runner pool migration\n"
            "☐ Renew the domain\n"
            "just a sentence\n"
        )
        return path

    async def test_reads_only_unchecked_todos(self, todo_file):
        items = await TodoSource({"globs": str(todo_file)}).fetch()

        assert {item.label for item in items} == {
            "Write tests for the retry path",
            "Chase the runner pool migration",
            "Renew the domain",
        }

    async def test_ids_survive_a_line_moving(self, todo_file):
        before = {i.label: i.id for i in await TodoSource({"globs": str(todo_file)}).fetch()}

        todo_file.write_text("- [ ] A new todo at the top\n" + todo_file.read_text())
        after = {i.label: i.id for i in await TodoSource({"globs": str(todo_file)}).fetch()}

        assert before["Renew the domain"] == after["Renew the domain"], (
            "inserting a line above must not re-create every task"
        )

    async def test_a_todo_can_reference_a_ticket(self, tmp_path):
        path = tmp_path / "t.md"
        path.write_text("- [ ] Write tests for ENG-42\n")

        item = (await TodoSource({"globs": str(path)}).fetch())[0]
        assert item.reference_keys == {"ENG-42"}

    async def test_check_fails_when_nothing_matches(self, tmp_path):
        from app.sources.base import SourceNotConfigured

        with pytest.raises(SourceNotConfigured):
            await TodoSource({"globs": str(tmp_path / "nope-*.md")}).check()


class TestMarkdown:
    async def test_title_comes_from_the_first_heading(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("# Runner pool migration plan\n\nSome content mentioning ENG-42.\n")

        item = (await MarkdownSource({"globs": str(path)}).fetch())[0]

        assert item.label == "Runner pool migration plan"
        assert item.source == "markdown"
        assert "ENG-42" in item.reference_keys

    async def test_a_doc_with_no_heading_falls_back_to_its_filename(self, tmp_path):
        path = tmp_path / "release-checklist.md"
        path.write_text("no heading here\n")

        assert (await MarkdownSource({"globs": str(path)}).fetch())[0].label == "Release Checklist"

    async def test_only_the_head_of_a_doc_is_scanned_for_refs(self, tmp_path):
        """A doc citing every ticket in the backlog would otherwise merge unrelated work."""
        path = tmp_path / "long.md"
        path.write_text("# Doc\n\n" + ("filler " * 1000) + "\nENG-99\n")

        item = (await MarkdownSource({"globs": str(path)}).fetch())[0]
        assert "ENG-99" not in item.reference_keys
