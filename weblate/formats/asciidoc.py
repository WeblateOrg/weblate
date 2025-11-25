"""
AsciiDoc file format support for Weblate.

This format handles .adoc files for documentation translation.
Based on the existing Markdown format.
"""

from django.utils.translation import gettext_lazy
from weblate.formats.convert import ConvertFormat
from weblate.formats.helpers import NamedBytesIO


class AsciiDocFormat(ConvertFormat):
    """AsciiDoc file format handler."""

    # Translators: File format name
    name = gettext_lazy("AsciiDoc file")
    autoload = ("*.adoc",)
    format_id = "asciidoc"
    check_flags = ("safe-html", "strict-same", "md-text")
    monolingual = True
    
    def _convert_adoc_to_html_path(self, adoc_path):
        """Convert AsciiDoc file path to HTML file path."""
        import os
                
        # Replace .adoc with .html
        html_path = adoc_path.replace('.adoc', '.html')
        
        # Insert 'htmlTemps' directory after the component directory
        # Split the path and insert htmlTemps after the component directory
        path_parts = html_path.split('/')
        
        # Find the position after 'vcs' and after the component directory
        vcs_index = None
        for i, part in enumerate(path_parts):
            if part == 'vcs':
                vcs_index = i
                break
        
        if vcs_index is not None and vcs_index + 1 < len(path_parts):
            # Insert 'htmlTemps' after the component directory (vcs + 2)
            path_parts.insert(vcs_index + 1, 'htmlTemps')
            html_path = '/'.join(path_parts)
            # Create directory structure if it doesn't exist
            os.makedirs(os.path.dirname(html_path), exist_ok=True)
        
        return html_path

    def convertfile(self, storefile, template_store):
        # Lazy import as mistletoe is expensive
        from translate.storage.html import htmlfile
        import os

        # Handle both file objects and string paths
        if isinstance(storefile, str):
            # storefile is a file path
            adoc_path = storefile
            with open(storefile, 'r', encoding='utf-8') as f:
                asciidoc_content = f.read()
        else:
            # storefile is a file object
            adoc_path = getattr(storefile, 'name', 'unknown.adoc')
            asciidoc_content = storefile.read()
            if isinstance(asciidoc_content, bytes):
                asciidoc_content = asciidoc_content.decode('utf-8')
        
        # Create HTML path using the conversion function
        html_path = self._convert_adoc_to_html_path(adoc_path)
        
        # If HTML file doesn't exist, create it from the .adoc file
        if not os.path.exists(html_path):
            # Convert AsciiDoc to HTML
            html_content = self._asciidoc_to_html(asciidoc_content)
            
            # Write HTML file
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        else:
            # Read existing HTML file
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
        
        # Repair broken HTML if needed
        html_content = self._repair_html_tags(html_content)
        
        # Create HTML parser with converted content
        html_bytes = html_content.encode('utf-8')
        htmlparser = htmlfile(inputfile=NamedBytesIO("", html_bytes))

        return self.convert_to_po(htmlparser, template_store)

    def save_content(self, handle) -> None:
        """Store content to file using HTML as intermediate format."""
        # Lazy import as mistletoe is expensive
        from translate.convert.po2html import po2html
        import pypandoc
        import tempfile
        import os

        # Parse the .adoc file and create corresponding .html file
        adoc_path = self.template_store.storefile
        if hasattr(adoc_path, "name"):
            adoc_path = adoc_path.name
        
        # Create HTML path using the conversion function
        html_path = self._convert_adoc_to_html_path(adoc_path)
        
        # If HTML file doesn't exist, create it from the .adoc file
        if not os.path.exists(html_path):
            with open(adoc_path, 'r', encoding='utf-8') as f:
                asciidoc_content = f.read()
            
            # Convert AsciiDoc to HTML
            html_content = self._asciidoc_to_html(asciidoc_content)
            
            # Write HTML file
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
        # Use po2html with the HTML template
        converter = po2html()
        with open(html_path, "rb") as templatefile:
            outputstring = converter.mergestore(
                self.store, templatefile, includefuzzy=True
            )
        
        # Validate and repair broken HTML tag structures
        outputstring = self._repair_html_tags(outputstring)

        adoc_path = self.storefile
        if hasattr(adoc_path, "name"):
            adoc_path = adoc_path.name
        
        # Create HTML path using the conversion function
        html_path = self._convert_adoc_to_html_path(adoc_path)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(outputstring)
            
        # Convert HTML back to AsciiDoc
        asciidoc_content = pypandoc.convert_text(outputstring, 'asciidoc', format='html')
        handle.write(asciidoc_content.encode('utf-8'))
            
    
    @staticmethod
    def _repair_html_tags(html_content):
        """
        Repair broken HTML tag structures caused by po2html merge process.
        
        Uses BeautifulSoup if available for robust HTML repair, otherwise
        falls back to regex-based pattern matching.
        """
        import re
        from translate.storage.html import htmlfile
        from weblate.formats.helpers import NamedBytesIO
        
        # First, try to validate the HTML by parsing it with the same parser Weblate uses
        try:
            html_bytes = html_content.encode('utf-8')
            htmlfile(inputfile=NamedBytesIO("", html_bytes))
            # If parsing succeeds, return as-is
            return html_content
        except Exception:
            # HTML has errors, try to repair
            pass
        
        # Try using BeautifulSoup for robust HTML repair
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            repaired_html = str(soup)
            # Validate the repaired HTML
            try:
                html_bytes = repaired_html.encode('utf-8')
                htmlfile(inputfile=NamedBytesIO("", html_bytes))
                return repaired_html
            except Exception:
                # BeautifulSoup repair didn't work, fall through to regex patterns
                pass
        except ImportError:
            # BeautifulSoup not available, use regex patterns
            pass
        
        # Repair pattern 1: <code>...<a>...</code></a> -> <code>...<a>...</a></code>
        # This happens when code tag is closed before anchor tag
        pattern1 = re.compile(
            r'(<code[^>]*>)(.*?)(<a\s+[^>]*>)(.*?)(</code>)(.*?)(</a>)',
            re.DOTALL
        )
        def fix_pattern1(match):
            code_open = match.group(1)
            before_anchor = match.group(2)
            anchor_open = match.group(3)
            anchor_content = match.group(4)
            code_close = match.group(5)
            after_code = match.group(6)
            anchor_close = match.group(7)
            # Reorder: code_open, before_anchor, anchor_open, anchor_content, anchor_close, after_code, code_close
            return f"{code_open}{before_anchor}{anchor_open}{anchor_content}{anchor_close}{after_code}{code_close}"
        
        html_content = pattern1.sub(fix_pattern1, html_content)
        
        # Repair pattern 2: <a>...<code>...</a></code> -> <a>...<code>...</code></a>
        # This happens when anchor tag is closed before code tag
        pattern2 = re.compile(
            r'(<a\s+[^>]*>)(.*?)(<code[^>]*>)(.*?)(</a>)(.*?)(</code>)',
            re.DOTALL
        )
        def fix_pattern2(match):
            anchor_open = match.group(1)
            before_code = match.group(2)
            code_open = match.group(3)
            code_content = match.group(4)
            anchor_close = match.group(5)
            after_anchor = match.group(6)
            code_close = match.group(7)
            # Reorder: anchor_open, before_code, code_open, code_content, code_close, after_anchor, anchor_close
            return f"{anchor_open}{before_code}{code_open}{code_content}{code_close}{after_anchor}{anchor_close}"
        
        html_content = pattern2.sub(fix_pattern2, html_content)
        
        # Repair pattern 3: Fix cases where closing tags are completely out of order
        # <code>text<a href="...">link</code></a> -> <code>text<a href="...">link</a></code>
        pattern3 = re.compile(
            r'(<code[^>]*>)([^<]*?)(<a\s+[^>]*>)([^<]*?)(</code>)([^<]*?)(</a>)',
            re.DOTALL
        )
        def fix_pattern3(match):
            code_open = match.group(1)
            before_anchor = match.group(2)
            anchor_open = match.group(3)
            anchor_content = match.group(4)
            code_close = match.group(5)
            between = match.group(6)
            anchor_close = match.group(7)
            return f"{code_open}{before_anchor}{anchor_open}{anchor_content}{anchor_close}{between}{code_close}"
        
        html_content = pattern3.sub(fix_pattern3, html_content)
        
        # Repair pattern 4: Fix specific common mismatches
        # <key>...</pre> -> <key>...</key> (when </pre> appears where </key> is expected)
        # This pattern looks for <key> followed by content and then </pre> where </key> should be
        pattern4 = re.compile(
            r'(<key[^>]*>)(.*?)(</pre>)',
            re.DOTALL | re.IGNORECASE
        )
        def fix_pattern4(match):
            key_open = match.group(1)
            content = match.group(2)
            # Check if there's a <pre> tag in the content that should be closed first
            if '<pre' in content.lower():
                # Find the matching </pre> and keep it, but also close </key>
                # This is complex, so just close </key> before </pre>
                return f"{key_open}{content}</key>"
            else:
                # No <pre> tag, so </pre> is wrong, replace with </key>
                return f"{key_open}{content}</key>"
        
        html_content = pattern4.sub(fix_pattern4, html_content)
        
        # Repair pattern 5: Fix </key> when </pre> is expected (reverse case)
        pattern5 = re.compile(
            r'(<pre[^>]*>)(.*?)(</key>)',
            re.DOTALL | re.IGNORECASE
        )
        def fix_pattern5(match):
            pre_open = match.group(1)
            content = match.group(2)
            return f"{pre_open}{content}</pre>"
        
        html_content = pattern5.sub(fix_pattern5, html_content)
        
        # Try parsing again to validate with the same parser Weblate uses
        try:
            html_bytes = html_content.encode('utf-8')
            htmlfile(inputfile=NamedBytesIO("", html_bytes))
            # Parsing succeeded, return repaired HTML
            return html_content
        except Exception as e:
            # If still broken, log but return the repaired version anyway
            # The convertfile method will catch parse errors during load
            import logging
            logger = logging.getLogger('weblate.formats.asciidoc')
            logger.warning(f"HTML repair attempted but still has parse errors: {e}")
            # Return the repaired version - it's better than the broken one
            return html_content
    
    @staticmethod
    def _asciidoc_to_html(asciidoc_content):
        """Convert AsciiDoc to HTML using Asciidoctor."""
        import tempfile
        import os
        import subprocess

        # Use Asciidoctor to convert AsciiDoc to HTML
        with tempfile.NamedTemporaryFile(mode='w', suffix='.adoc', delete=False) as asciidoc_file:
            asciidoc_file.write(asciidoc_content)
            asciidoc_path = asciidoc_file.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as html_file:
            html_path = html_file.name

        try:
            # Convert AsciiDoc to HTML using Asciidoctor
            result = subprocess.run([
                'asciidoctor',
                '-b', 'html5',
                '-o', html_path,
                asciidoc_path
            ], capture_output=True, text=True, check=True)

            # Read the HTML content
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            return html_content

        except subprocess.CalledProcessError as e:
            raise Exception(f"Asciidoctor conversion failed: {e.stderr}")
        finally:
            # Clean up temporary files
            os.unlink(asciidoc_path)
            os.unlink(html_path)
    

    # @staticmethod
    # def get_language_code(filename: str, language_code_style: str = None) -> str:
    #     """Extract language code from filename."""
    #     import re
        
    #     # For base files like intro.adoc, return the source language code
    #     if not re.search(r'_[a-z]{2}(_[A-Za-z]{2,4})?\.adoc$', filename):
    #         return 'en'  # Return source language code for base files
        
    #     # For translated files like intro_es.adoc, intro_zh_Hans.adoc, extract language code
    #     match = re.search(r'_([a-z]{2})(_[A-Za-z]{2,4})?\.adoc$', filename)
    #     if match:
    #         return match.group(1)
        
    #     # If no language code found, return None (not 'en')
    #     # This allows Weblate to handle the file properly
    #     return None

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/asciidoc"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "adoc"