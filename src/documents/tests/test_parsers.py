from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings

from documents.parsers import get_default_file_extension
from documents.parsers import get_supported_file_extensions
from documents.parsers import is_file_ext_supported
from documents.parsers import resolve_archive_preference
from paperless.parsers.registry import get_parser_registry
from paperless.parsers.registry import reset_parser_registry
from paperless.parsers.tesseract import RasterisedDocumentParser
from paperless.parsers.text import TextDocumentParser
from paperless.parsers.tika import TikaDocumentParser


class TestParserAvailability(TestCase):
    def test_tesseract_parser(self) -> None:
        """
        GIVEN:
            - Various mime types
        WHEN:
            - The parser class is instantiated
        THEN:
            - The Tesseract based parser is return
        """
        supported_mimes_and_exts = [
            ("application/pdf", ".pdf"),
            ("image/png", ".png"),
            ("image/jpeg", ".jpg"),
            ("image/tiff", ".tif"),
            ("image/webp", ".webp"),
        ]

        supported_exts = get_supported_file_extensions()

        for mime_type, ext in supported_mimes_and_exts:
            self.assertIn(ext, supported_exts)
            self.assertEqual(get_default_file_extension(mime_type), ext)
            self.assertIsInstance(
                get_parser_registry().get_parser_for_file(mime_type, "")(),
                RasterisedDocumentParser,
            )

    def test_text_parser(self) -> None:
        """
        GIVEN:
            - Various mime types of a text form
        WHEN:
            - The parser class is instantiated
        THEN:
            - The text based parser is return
        """
        supported_mimes_and_exts = [
            ("text/plain", ".txt"),
            ("text/csv", ".csv"),
        ]

        supported_exts = get_supported_file_extensions()

        for mime_type, ext in supported_mimes_and_exts:
            self.assertIn(ext, supported_exts)
            self.assertEqual(get_default_file_extension(mime_type), ext)
            self.assertIsInstance(
                get_parser_registry().get_parser_for_file(mime_type, "")(),
                TextDocumentParser,
            )

    def test_tika_parser(self) -> None:
        """
        GIVEN:
            - Various mime types of a office document form
        WHEN:
            - The parser class is instantiated
        THEN:
            - The Tika/Gotenberg based parser is return
        """
        supported_mimes_and_exts = [
            ("application/vnd.oasis.opendocument.text", ".odt"),
            ("text/rtf", ".rtf"),
            ("application/msword", ".doc"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".docx",
            ),
        ]

        self.addCleanup(reset_parser_registry)

        # Reset and rebuild the registry with Tika enabled.
        with override_settings(TIKA_ENABLED=True):
            reset_parser_registry()
            supported_exts = get_supported_file_extensions()

            for mime_type, ext in supported_mimes_and_exts:
                self.assertIn(ext, supported_exts)
                self.assertEqual(get_default_file_extension(mime_type), ext)
                self.assertIsInstance(
                    get_parser_registry().get_parser_for_file(mime_type, "")(),
                    TikaDocumentParser,
                )

    def test_no_parser_for_mime(self) -> None:
        self.assertIsNone(get_parser_registry().get_parser_for_file("text/sdgsdf", ""))

    def test_default_extension(self) -> None:
        # Test no parser declared still returns a an extension
        self.assertEqual(get_default_file_extension("application/zip"), ".zip")

        # Test invalid mimetype returns no extension
        self.assertEqual(get_default_file_extension("aasdasd/dgfgf"), "")

    def test_file_extension_support(self) -> None:
        self.assertTrue(is_file_ext_supported(".pdf"))
        self.assertFalse(is_file_ext_supported(".hsdfh"))
        self.assertFalse(is_file_ext_supported(""))


class TestResolveArchivePreference(TestCase):
    """Test the resolve_archive_preference function with various settings and file types."""

    def setUp(self):
        """Set up test PDF file for mocking."""
        from pathlib import Path

        self.test_pdf_path = Path("/fake/path/test.pdf")

    @override_settings(ARCHIVE_FILE_GENERATION="always")
    def test_always_setting_with_capable_parser(self):
        """Test ARCHIVE_FILE_GENERATION=always with parser that can produce archive."""
        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=True,
        )
        self.assertTrue(result)

    @override_settings(ARCHIVE_FILE_GENERATION="always")
    def test_always_setting_with_incapable_parser(self):
        """Test ARCHIVE_FILE_GENERATION=always with parser that cannot produce archive."""
        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=False,
        )
        self.assertFalse(result)

    @override_settings(ARCHIVE_FILE_GENERATION="never")
    def test_never_setting_regardless_of_parser(self):
        """Test ARCHIVE_FILE_GENERATION=never regardless of parser capability."""
        # Test with capable parser
        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=True,
        )
        self.assertFalse(result)

        # Test with incapable parser
        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=False,
        )
        self.assertFalse(result)

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    def test_auto_setting_with_non_pdf_mime_type(self):
        """Test ARCHIVE_FILE_GENERATION=auto with non-PDF mime types."""
        # Non-PDF mime types (images etc.) should always produce archive
        result = resolve_archive_preference(
            "image/jpeg",
            self.test_pdf_path,  # Path doesn't matter for non-PDF
            can_produce_archive=True,
        )
        self.assertTrue(result)

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    @patch("documents.parsers._should_produce_archive_for_pdf")
    def test_auto_setting_with_pdf_delegates_to_heuristic(self, mock_heuristic):
        """Test ARCHIVE_FILE_GENERATION=auto with PDF delegates to heuristic function."""
        mock_heuristic.return_value = False

        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=True,
        )

        mock_heuristic.assert_called_once_with(self.test_pdf_path)
        self.assertFalse(result)

        # Test with heuristic returning True
        mock_heuristic.reset_mock()
        mock_heuristic.return_value = True

        result = resolve_archive_preference(
            "application/pdf",
            self.test_pdf_path,
            can_produce_archive=True,
        )

        mock_heuristic.assert_called_once_with(self.test_pdf_path)
        self.assertTrue(result)

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    @patch("documents.parsers.run_subprocess")
    @patch("documents.parsers.pikepdf.open")
    @patch("documents.parsers.read_file_handle_unicode_errors")
    def test_pdf_heuristic_born_digital_tagged(
        self,
        mock_read_file,
        mock_pikepdf_open,
        mock_subprocess,
    ):
        """Test PDF heuristic detects born-digital tagged PDF (should NOT produce archive)."""
        # Mock pdftotext output - lots of text
        mock_read_file.return_value = (
            "This is a lot of text content from a born-digital PDF document."
        )

        # Mock pikepdf - tagged PDF
        mock_pdf = Mock()
        mock_pdf.Root = Mock()
        mock_pdf.Root.StructTreeRoot = Mock()  # Has structure tree
        mock_pikepdf_open.return_value.__enter__.return_value = mock_pdf

        from documents.parsers import _should_produce_archive_for_pdf

        result = _should_produce_archive_for_pdf(self.test_pdf_path)

        self.assertFalse(result)  # Born-digital tagged PDF should NOT produce archive
        mock_subprocess.assert_called_once()
        mock_pikepdf_open.assert_called_once_with(self.test_pdf_path)

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    @patch("documents.parsers.run_subprocess")
    @patch("documents.parsers.pikepdf.open")
    @patch("documents.parsers.read_file_handle_unicode_errors")
    def test_pdf_heuristic_scanner_ocr_untagged(
        self,
        mock_read_file,
        mock_pikepdf_open,
        mock_subprocess,
    ):
        """Test PDF heuristic detects scanner OCR'd untagged PDF (should produce archive)."""
        # Mock pdftotext output - lots of text
        mock_read_file.return_value = (
            "This is a lot of text content from a scanner OCR'd PDF document."
        )

        # Mock pikepdf - untagged PDF
        mock_pdf = Mock()
        mock_pdf.Root = Mock()
        # No StructTreeRoot and MarkInfo.Marked is False
        del mock_pdf.Root.StructTreeRoot  # Simulate no attribute
        mock_pdf.Root.MarkInfo = Mock()
        mock_pdf.Root.MarkInfo.get.return_value = False
        mock_pikepdf_open.return_value.__enter__.return_value = mock_pdf

        from documents.parsers import _should_produce_archive_for_pdf

        result = _should_produce_archive_for_pdf(self.test_pdf_path)

        self.assertTrue(result)  # Scanner OCR'd PDF should produce archive
        mock_subprocess.assert_called_once()
        mock_pikepdf_open.assert_called_once_with(self.test_pdf_path)

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    @patch("documents.parsers.run_subprocess")
    @patch("documents.parsers.pikepdf.open")
    @patch("documents.parsers.read_file_handle_unicode_errors")
    def test_pdf_heuristic_raw_scan_no_text(
        self,
        mock_read_file,
        mock_pikepdf_open,
        mock_subprocess,
    ):
        """Test PDF heuristic detects raw scan with no text (should produce archive)."""
        # Mock pdftotext output - very little text
        mock_read_file.return_value = "  "  # Just whitespace

        # Mock pikepdf - doesn't matter for this case
        mock_pdf = Mock()
        mock_pdf.Root = Mock()
        mock_pikepdf_open.return_value.__enter__.return_value = mock_pdf

        from documents.parsers import _should_produce_archive_for_pdf

        result = _should_produce_archive_for_pdf(self.test_pdf_path)

        self.assertTrue(result)  # Raw scan should produce archive
        mock_subprocess.assert_called_once()
        # pikepdf check is not needed when text is short, but we don't control that here

    @override_settings(ARCHIVE_FILE_GENERATION="auto")
    @patch(
        "documents.parsers.run_subprocess",
        side_effect=Exception("pdftotext failed"),
    )
    def test_pdf_heuristic_exception_handling(self, mock_subprocess):
        """Test PDF heuristic defaults to producing archive when exception occurs."""
        from documents.parsers import _should_produce_archive_for_pdf

        result = _should_produce_archive_for_pdf(self.test_pdf_path)

        self.assertTrue(result)  # Should default to True when exception occurs
        mock_subprocess.assert_called_once()
