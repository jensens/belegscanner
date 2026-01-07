"""Email to PDF conversion using weasyprint."""

import html
from datetime import datetime
from pathlib import Path

from weasyprint import HTML


class EmailPdfService:
    """Convert email content to PDF.

    Uses weasyprint to render HTML to PDF. Supports both plain text
    and HTML email bodies, with proper header information display.
    """

    def create_pdf(
        self,
        sender: str,
        subject: str,
        date: datetime,
        message_id: str,
        body_text: str,
        body_html: str | None,
        output_path: Path,
    ) -> bool:
        """Create PDF from email content.

        Args:
            sender: Email sender address.
            subject: Email subject line.
            date: Email date.
            message_id: Email Message-ID header.
            body_text: Plain text body (used if no HTML).
            body_html: HTML body (preferred if available).
            output_path: Path to save the PDF.

        Returns:
            True if PDF was created successfully, False otherwise.
        """
        try:
            # Generate HTML
            html_content = self._generate_html(
                sender=sender,
                subject=subject,
                date=date,
                message_id=message_id,
                body_text=body_text,
                body_html=body_html,
            )

            # Create parent directories if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Render to PDF
            HTML(string=html_content).write_pdf(output_path)

            return True
        except Exception:
            return False

    def _generate_html(
        self,
        sender: str,
        subject: str,
        date: datetime,
        message_id: str,
        body_text: str,
        body_html: str | None,
    ) -> str:
        """Generate HTML document from email content.

        Args:
            sender: Email sender address.
            subject: Email subject line.
            date: Email date.
            message_id: Email Message-ID header.
            body_text: Plain text body.
            body_html: HTML body (optional).

        Returns:
            Complete HTML document string.
        """
        # Format date in German format
        date_str = date.strftime("%d.%m.%Y %H:%M")

        # Escape values for HTML
        sender_escaped = html.escape(sender)
        subject_escaped = html.escape(subject)
        message_id_escaped = html.escape(message_id)

        # Prepare body content
        if body_html:
            # Use HTML body directly (it's already HTML)
            body_content = body_html
        else:
            # Wrap plain text in <pre> for formatting preservation
            body_escaped = html.escape(body_text)
            pre_style = "white-space: pre-wrap; word-wrap: break-word; font-family: monospace;"
            body_content = f'<pre style="{pre_style}">{body_escaped}</pre>'

        return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>{subject_escaped}</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
        }}
        .header {{
            border-bottom: 2px solid #2196F3;
            padding-bottom: 1em;
            margin-bottom: 1.5em;
        }}
        .header-row {{
            margin: 0.3em 0;
        }}
        .header-label {{
            font-weight: bold;
            color: #666;
            display: inline-block;
            width: 100px;
        }}
        .header-value {{
            color: #333;
        }}
        .subject {{
            font-size: 14pt;
            font-weight: bold;
            margin: 0.5em 0;
            color: #1976D2;
        }}
        .message-id {{
            font-size: 9pt;
            color: #999;
            font-family: monospace;
        }}
        .body {{
            margin-top: 1em;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 1em;
            border-radius: 4px;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="subject">{subject_escaped}</div>
        <div class="header-row">
            <span class="header-label">Von:</span>
            <span class="header-value">{sender_escaped}</span>
        </div>
        <div class="header-row">
            <span class="header-label">Datum:</span>
            <span class="header-value">{date_str}</span>
        </div>
        <div class="header-row message-id">
            <span class="header-label">Message-ID:</span>
            <span class="header-value">{message_id_escaped}</span>
        </div>
    </div>
    <div class="body">
        {body_content}
    </div>
</body>
</html>"""
