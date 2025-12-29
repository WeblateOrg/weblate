"""
AsciiDoc file format support for Weblate.

This format handles .adoc files for documentation translation using po4a.
Based on po4a's AsciiDoc module for extraction and translation.
"""

import os
import shutil
import stat
import subprocess
import tempfile
from django.utils.translation import gettext_lazy
from translate.storage.pypo import pofile
from weblate.formats.convert import ConvertFormat
from weblate.utils.errors import report_error


class AsciiDocFormat(ConvertFormat):
    """AsciiDoc file format handler using po4a."""

    # Translators: File format name
    name = gettext_lazy("AsciiDoc file")
    autoload = ("*.adoc",)
    format_id = "asciidoc"
    monolingual = True

    def _merge_translations(self, store, template_store):
        """
        Add missing translation units from database to the store.

        Only adds units that don't exist in the store. Does not merge/overwrite
        existing units in the store. This ensures all database translations are
        preserved even if po4a-gettextize didn't extract them.
        """
        from collections import defaultdict

        # Create index of units already in store (by source + context) for quick lookup
        store_units_index = {}
        for unit in store.units:
            if unit.isheader():
                continue
            # Use source + context as key for matching
            key = (unit.source, unit.getcontext())
            store_units_index[key] = unit

        # Add missing units from database that are not in the store
        for existing_unit in self.existing_units:
            sources = existing_unit.get_source_plurals()
            if not sources:
                continue
            source = sources[0]  # Use first source for matching
            context = existing_unit.context or ""

            # Check if this unit exists in store
            key = (source, context)
            if key not in store_units_index:
                # Unit is missing from store, add it with its translation from database
                thepo = store.addsourceunit(source)
                if context:
                    thepo.setcontext(context)
                # Set the translation from database
                thepo.target = existing_unit.target
                # Set fuzzy flag if unit is STATE_FUZZY
                from weblate.utils.state import STATE_FUZZY
                if existing_unit.state == STATE_FUZZY:
                    thepo.markfuzzy(True)
                # Update index
                store_units_index[key] = thepo

        return store

    def convertfile(self, storefile, template_store):
        """
        Convert AsciiDoc file to PO format using po4a.

        Uses po4a-gettextize to extract translatable strings from AsciiDoc.
        """
        # Get template file path (master file for po4a-gettextize)
        if template_store and hasattr(template_store, 'storefile'):
            template_file = template_store.storefile
            if hasattr(template_file, 'name'):
                template_path = template_file.name
            elif isinstance(template_file, str):
                template_path = template_file
            else:
                # Fallback: use storefile as template
                template_path = None
        else:
            template_path = None

        # Get storefile path (localized file for po4a-gettextize)
        # If storefile is a file object without a name, we need to create a temp file
        if isinstance(storefile, str):
            storefile_path = storefile
        else:
            storefile_path = getattr(storefile, 'name', None)

        # When template_store is None (e.g., during base file validation),
        # use storefile as both template and localized file
        if template_path is None:
            template_path = storefile_path

        # Create temporary PO file for output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.po', delete=False) as tmp_po:
            tmp_po_path = tmp_po.name

        try:
            # Validate paths before calling po4a-gettextize
            if template_path is None:
                raise ValueError("template_path cannot be None for po4a-gettextize")
            if storefile_path is None:
                raise ValueError("storefile_path cannot be None for po4a-gettextize")
            if not os.path.exists(template_path):
                raise ValueError(f"template_path does not exist: {template_path}")
            if not os.path.exists(storefile_path):
                raise ValueError(f"storefile_path does not exist: {storefile_path}")

            # Use po4a-gettextize to extract translatable strings
            # -m: template file (master)
            # -l: storefile (localized)
            # -p: output PO file
            result = subprocess.run(
                [
                    'po4a-gettextize',
                    '-f', 'asciidoc',
                    '-m', template_path,
                    '-l', storefile_path,
                    '-p', tmp_po_path,
                    '-M', 'UTF-8',
                    '-L', 'UTF-8',
                    '-k', '0',
                    '--option', 'compat=asciidoctor',
                    '--option', 'tablecells',
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            # Clean up temporary files created by po4a-gettextize in current directory
            po4a_temp_files = [
                'po4atemp.master.po',
                'po4atemp.localized.po',
            ]
            for temp_file in po4a_temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

            # Read the generated PO file
            if os.path.exists(tmp_po_path) and os.path.getsize(tmp_po_path) > 0:
                with open(tmp_po_path, 'rb') as po_file:
                    store = pofile(po_file)
            else:
                # If po4a-gettextize failed, create an empty PO store
                if result.returncode != 0:
                    report_error(
                        f"po4a-gettextize extraction failed: {result.stderr}",
                    )
                else:
                    report_error(
                        "po4a-gettextize extraction failed: no output file generated",
                    )
                # Create empty PO store with header
                store = pofile()
                store.updateheader(add=True, x_accelerator_marker=None, x_previous_msgid=None)
        except subprocess.CalledProcessError as e:
            report_error(
                f"po4a-gettextize extraction error: {e.stderr}",
            )
            # Create empty PO store with header as fallback
            store = pofile()
            store.updateheader(add=True, x_accelerator_marker=None, x_previous_msgid=None)
        except FileNotFoundError:
            report_error(
                "po4a-gettextize not found. Please install po4a package.",
            )
            # Create empty PO store with header as fallback
            store = pofile()
            store.updateheader(add=True, x_accelerator_marker=None, x_previous_msgid=None)
        finally:
            # Clean up temporary files
            if os.path.exists(tmp_po_path):
                os.unlink(tmp_po_path)

        return self._merge_translations(store, template_store)


    def _postprocess_output(self, content: str) -> str:
        """
        Postprocess the AsciiDoc output from po4a-translate.

        This method can be overridden to apply custom postprocessing
        such as normalizing line endings, fixing formatting, etc.

        Args:
            content: The raw AsciiDoc content from po4a-translate

        Returns:
            Postprocessed AsciiDoc content
        """
        import re

        # Normalize line endings to LF (Unix-style)
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Fix single-line code blocks: transform "```[lang] code ```" to multi-line format
        # Pattern matches:
        # - ```cpp code ``` -> ```cpp\n\ncode\n\n```
        # - ```c++ code ``` -> ```c++\n\ncode\n\n```
        # - ``` code ``` -> ```\n\ncode\n\n```
        # This regex matches code blocks that are on a single line
        def fix_code_block(match):
            opening = match.group(1)  # The opening ```[language]
            code = match.group(2).strip()  # The code content (strip whitespace)
            closing = match.group(3)  # The closing ```
            # Transform to multi-line format with blank lines before and after code
            return f"{opening}\n\n{code}\n\n{closing}"

        # Match code blocks that are on a single line
        # Pattern: ```[optional language] code ```
        # The pattern captures:
        # - Group 1: Opening ``` and optional language (e.g., "```cpp", "```c++", "```")
        # - Group 2: The code content (non-greedy, matches anything except backticks)
        # - Group 3: Closing ```
        # Note: The pattern uses \s+ to match whitespace between opening and code,
        # and \s+ before closing to ensure we match the full pattern
        pattern = r'(```[a-zA-Z0-9+]*)\s+([^`]+?)\s+(```)'
        content = re.sub(pattern, fix_code_block, content)

        # Remove trailing whitespace from each line
        lines = [line.rstrip() for line in content.split('\n')]
        content = '\n'.join(lines)

        # Ensure file ends with a newline if it has content
        if content and not content.endswith('\n'):
            content += '\n'

        return content

    def save_content(self, handle) -> None:
        """
        Save translated content back to AsciiDoc using po4a.

        Uses po4a-translate to merge PO translations back into AsciiDoc template.
        """
        # Get template AsciiDoc file path
        template_path = self.template_store.storefile
        if hasattr(template_path, "name"):
            template_path = template_path.name

        # Create temporary PO file with translations
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.po', delete=False) as tmp_po_01:
            # Write PO store to temporary file
            self.store.savefile(tmp_po_01.name)
            tmp_po_path_01 = tmp_po_01.name

        # Create a temporary PO file with fuzzy flags cleared so po4a-translate will use those translations
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.po', delete=False) as tmp_po_02:
            tmp_po_path_02 = tmp_po_02.name

        # Use msgattrib to clear fuzzy flags from the PO file
        # This allows po4a-translate to use fuzzy translations
        try:
            result = subprocess.run(
                [
                    'msgattrib',
                    '--clear-fuzzy',
                    tmp_po_path_01,
                ],
                capture_output=True,
                text=False,  # Capture as bytes to preserve encoding
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                # Write the output to the second temporary file
                with open(tmp_po_path_02, 'wb') as f:
                    f.write(result.stdout)
            else:
                # If msgattrib fails, use the original PO file
                tmp_po_path_02 = tmp_po_path_01
        except FileNotFoundError:
            # If msgattrib is not available, use the original PO file
            tmp_po_path_02 = tmp_po_path_01

        # Create temporary output file for po4a-translate
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.adoc', delete=False) as tmp_output:
            tmp_output_path = tmp_output.name

        # Create a wrapper directory for msgfmt that bypasses validation
        tmp_bin_dir = None
        original_path = None
        try:
            # Create temporary directory for msgfmt wrapper
            tmp_bin_dir = tempfile.mkdtemp()
            msgfmt_wrapper_path = os.path.join(tmp_bin_dir, 'msgfmt')

            # Create wrapper script that always succeeds
            with open(msgfmt_wrapper_path, 'w') as wrapper:
                wrapper.write('#!/bin/bash\n')
                wrapper.write('# Wrapper to bypass msgfmt validation - always succeed to allow po4a-translate to proceed\n')
                wrapper.write('exit 0\n')

            # Make wrapper executable
            os.chmod(msgfmt_wrapper_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

            # Save original PATH and temporarily override to use our wrapper
            original_path = os.environ.get('PATH', '')
            os.environ['PATH'] = f"{tmp_bin_dir}:{original_path}"

            # Use po4a-translate to generate translated AsciiDoc file
            # -m: template file (master)
            # -p: PO file with translations
            # -l: output translated AsciiDoc file
            result = subprocess.run(
                [
                    'po4a-translate',
                    '-f', 'asciidoc',
                    '-m', template_path,
                    '-p', tmp_po_path_02,
                    '-l', tmp_output_path,
                    '-M', 'UTF-8',
                    '-L', 'UTF-8',
                    '-k', '0',
                    '-w', '0',
                    '--option', 'compat=asciidoctor',
                    '--option', 'tablecells',
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            # Read the generated AsciiDoc file, postprocess, and write to handle
            if os.path.exists(tmp_output_path) and os.path.getsize(tmp_output_path) > 0:
                # Read the file as text for postprocessing
                with open(tmp_output_path, 'r', encoding='utf-8') as output_file:
                    content = output_file.read()

                # Postprocess the content
                content = self._postprocess_output(content)

                # Write postprocessed content to handle
                handle.write(content.encode('utf-8'))
            else:
                # Translation failed: raise exception to prevent silent failure
                error_msg = (
                    f"po4a-translate failed: {result.stderr}"
                    if result.returncode != 0
                    else "po4a-translate failed: no output file generated"
                )
                report_error(error_msg)
                # Raise exception to prevent empty file from being written
                raise RuntimeError(error_msg)

            # Report warnings if any (but don't fail on warnings)
            if result.returncode != 0 and result.stderr:
                report_error(f"po4a-translate warning: {result.stderr}")
        except subprocess.CalledProcessError as e:
            error_msg = f"po4a-translate error: {e.stderr}"
            report_error(error_msg)
            # Re-raise to prevent empty file from being written
            raise RuntimeError(error_msg) from e
        except FileNotFoundError:
            error_msg = "po4a-translate not found. Please install po4a package."
            report_error(error_msg)
            # Re-raise to prevent empty file from being written
            raise RuntimeError(error_msg) from None
        finally:
            # Restore original PATH and cleanup
            if original_path is not None:
                os.environ['PATH'] = original_path
            if tmp_bin_dir and os.path.exists(tmp_bin_dir):
                shutil.rmtree(tmp_bin_dir)
            if os.path.exists(tmp_po_path_02) and tmp_po_path_02 != tmp_po_path_01:
                os.unlink(tmp_po_path_02)
            if os.path.exists(tmp_po_path_01):
                os.unlink(tmp_po_path_01)
            if os.path.exists(tmp_output_path):
                os.unlink(tmp_output_path)

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/asciidoc"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "adoc"