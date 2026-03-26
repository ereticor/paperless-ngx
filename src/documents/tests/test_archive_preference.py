"""
Tests for documents.parsers.resolve_archive_preference function and related logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from pytest_django.fixtures import SettingsWrapper
    from pytest_mock import MockerFixture

from documents.parsers import _should_produce_archive_for_pdf
from documents.parsers import resolve_archive_preference
from paperless.models import ArchiveFileGenerationChoices


class TestResolveArchivePreference:
    """Test the resolve_archive_preference function."""

    @pytest.mark.parametrize(
        ("archive_setting", "can_produce_archive", "expected"),
        [
            pytest.param(
                ArchiveFileGenerationChoices.ALWAYS,
                True,
                True,
                id="always-capable-parser",
            ),
            pytest.param(
                ArchiveFileGenerationChoices.ALWAYS,
                False,
                False,
                id="always-incapable-parser",
            ),
            pytest.param(
                ArchiveFileGenerationChoices.NEVER,
                True,
                False,
                id="never-capable-parser",
            ),
            pytest.param(
                ArchiveFileGenerationChoices.NEVER,
                False,
                False,
                id="never-incapable-parser",
            ),
        ],
    )
    def test_archive_generation_setting_behavior(
        self,
        settings: SettingsWrapper,
        archive_setting: ArchiveFileGenerationChoices,
        can_produce_archive: bool,  # noqa: FBT001
        expected: bool,  # noqa: FBT001
    ) -> None:
        """Test archive generation setting behavior for always/never modes."""
        settings.ARCHIVE_FILE_GENERATION = archive_setting

        result = resolve_archive_preference(
            "application/pdf",
            Path("/fake/path.pdf"),
            can_produce_archive=can_produce_archive,
        )

        assert result is expected

    def test_auto_mode_non_pdf_returns_true(
        self,
        settings: SettingsWrapper,
    ) -> None:
        """
        GIVEN:
            - ARCHIVE_FILE_GENERATION=auto
            - Non-PDF mime type
            - can_produce_archive=True
        WHEN:
            - resolve_archive_preference is called
        THEN:
            - Returns True (images always need archive)
        """
        settings.ARCHIVE_FILE_GENERATION = ArchiveFileGenerationChoices.AUTO

        result = resolve_archive_preference(
            "image/jpeg",
            Path("/fake/path.jpg"),
            can_produce_archive=True,
        )

        assert result is True

    def test_auto_mode_pdf_delegates_to_heuristic(
        self,
        settings: SettingsWrapper,
        mocker: MockerFixture,
    ) -> None:
        """
        GIVEN:
            - ARCHIVE_FILE_GENERATION=auto
            - PDF mime type
            - can_produce_archive=True
        WHEN:
            - resolve_archive_preference is called
        THEN:
            - Delegates to _should_produce_archive_for_pdf
        """
        settings.ARCHIVE_FILE_GENERATION = ArchiveFileGenerationChoices.AUTO
        mock_heuristic = mocker.patch(
            "documents.parsers._should_produce_archive_for_pdf",
            return_value=True,
        )
        fake_path = Path("/fake/path.pdf")

        result = resolve_archive_preference(
            "application/pdf",
            fake_path,
            can_produce_archive=True,
        )

        mock_heuristic.assert_called_once_with(fake_path)
        assert result is True


class TestShouldProduceArchiveForPdf:
    """Test the _should_produce_archive_for_pdf heuristic function."""

    @pytest.mark.parametrize(
        ("text_content", "has_struct_tree", "is_marked", "expected"),
        [
            pytest.param(
                "This is a long text content that is definitely longer than fifty characters",
                True,
                False,
                False,
                id="tagged-with-struct-tree",
            ),
            pytest.param(
                "This is a long text content that is definitely longer than fifty characters",
                False,
                True,
                False,
                id="tagged-with-mark-info",
            ),
            pytest.param(
                "This is a long text content that is definitely longer than fifty characters",
                False,
                False,
                True,
                id="untagged-with-text",
            ),
            pytest.param(
                "Short text",
                True,
                False,
                True,
                id="little-text-tagged",
            ),
            pytest.param(
                "Short text",
                False,
                False,
                True,
                id="little-text-untagged",
            ),
            pytest.param(
                "",
                False,
                False,
                True,
                id="no-text",
            ),
        ],
    )
    def test_pdf_heuristic_logic(
        self,
        mocker: MockerFixture,
        text_content: str,
        has_struct_tree: bool,  # noqa: FBT001
        is_marked: bool,  # noqa: FBT001
        expected: bool,  # noqa: FBT001
    ) -> None:
        """Test the PDF heuristic with various text and tagging combinations."""
        # Mock text extraction
        mocker.patch(
            "documents.parsers.run_subprocess",
        )
        mocker.patch(
            "documents.parsers.read_file_handle_unicode_errors",
            return_value=text_content,
        )

        # Mock pikepdf
        mock_pdf = Mock()
        if has_struct_tree:
            mock_pdf.Root.StructTreeRoot = True
        else:
            del mock_pdf.Root.StructTreeRoot

        mock_pdf.Root.MarkInfo.get.return_value = is_marked
        mock_pikepdf = mocker.patch("documents.parsers.pikepdf")
        mock_pikepdf.open.return_value.__enter__.return_value = mock_pdf

        result = _should_produce_archive_for_pdf(Path("/fake/path.pdf"))
        assert result is expected

    def test_exception_handling_returns_true(
        self,
        mocker: MockerFixture,
    ) -> None:
        """
        GIVEN:
            - PDF processing raises an exception
        WHEN:
            - _should_produce_archive_for_pdf is called
        THEN:
            - Returns True (safe default)
        """
        # Mock exception during text processing
        mocker.patch(
            "documents.parsers.run_subprocess",
            side_effect=Exception("Test error"),
        )

        result = _should_produce_archive_for_pdf(Path("/fake/path.pdf"))
        assert result is True

    def test_pikepdf_exception_returns_true(
        self,
        mocker: MockerFixture,
    ) -> None:
        """
        GIVEN:
            - Text extraction succeeds but pikepdf raises exception
        WHEN:
            - _should_produce_archive_for_pdf is called
        THEN:
            - Returns True (safe default)
        """
        # Mock successful text extraction
        mocker.patch("documents.parsers.run_subprocess")
        mocker.patch(
            "documents.parsers.read_file_handle_unicode_errors",
            return_value="This is a long text content that is definitely longer than fifty characters",
        )

        # Mock pikepdf exception
        mocker.patch(
            "documents.parsers.pikepdf.open",
            side_effect=Exception("PDF error"),
        )

        result = _should_produce_archive_for_pdf(Path("/fake/path.pdf"))
        assert result is True
