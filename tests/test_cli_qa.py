"""Tests for hivalidate.cli.qa's own logic -- just --reassess parsing/validation.
The review loop itself (including reassess_classes' actual effect) is tested
against hivalidate.qa.run_qa_session directly in test_qa.py.
"""

import pytest

from hivalidate.cli import qa as cli_qa


class TestParseReassess:
    def test_none_or_empty_returns_none(self):
        assert cli_qa._parse_reassess(None) is None
        assert cli_qa._parse_reassess("") is None

    def test_parses_a_comma_separated_list_into_a_set(self):
        assert cli_qa._parse_reassess("uncertain,duplicate") == {"uncertain", "duplicate"}

    def test_strips_whitespace_around_each_class(self):
        assert cli_qa._parse_reassess(" uncertain , duplicate ") == {"uncertain", "duplicate"}

    def test_single_class_is_fine(self):
        assert cli_qa._parse_reassess("uncertain") == {"uncertain"}

    def test_unknown_class_raises_a_clear_error(self):
        with pytest.raises(SystemExit, match="bogus"):
            cli_qa._parse_reassess("uncertain,bogus")
