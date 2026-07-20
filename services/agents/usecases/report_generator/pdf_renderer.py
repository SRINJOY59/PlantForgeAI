"""PDF generation and plotting utility for asset reports.

Parses Markdown reports into ReportLab Flowables and generates supporting charts
with Matplotlib.
"""

import io
import re
import matplotlib
matplotlib.use('Agg')  # headless backend for server execution
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Canvas that implements a two-pass page numbering ('Page X of Y')
    along with running headers and footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor('#64748b'))

        # Running Header (on page 2 and later)
        if self._pageNumber > 1:
            self.drawString(54, 750, "PlantMind Asset Condition Report")
            self.setStrokeColor(colors.HexColor('#e2e8f0'))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

        # Running Footer (on all pages)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        self.drawString(54, 40, "CONFIDENTIAL — PlantMind Operations Intelligence")
        self.setStrokeColor(colors.HexColor('#e2e8f0'))
        self.setLineWidth(0.5)
        self.line(54, 52, 558, 52)

        self.restoreState()


def generate_failure_chart(failure_data: list[dict]) -> io.BytesIO | None:
    """Generates a styled horizontal bar chart of failure modes and counts.
    Returns a BytesIO buffer with PNG bytes, or None if no failure history is found.
    """
    if not failure_data:
        return None

    # Filter out entries with zero counts and sort by count descending
    sorted_failures = sorted(
        [f for f in failure_data if f.get("count", 0) > 0],
        key=lambda x: x["count"],
        reverse=True
    )

    if not sorted_failures:
        return None

    modes = [f["mode"] for f in sorted_failures]
    counts = [f["count"] for f in sorted_failures]

    # Style definitions matching modern UI
    fig, ax = plt.subplots(figsize=(6, 2.8))
    
    # Horizontal bar chart works best for long labels
    y_pos = range(len(modes))
    bars = ax.barh(y_pos, counts, color='#0284c7', edgecolor='#0369a1', height=0.6)
    
    ax.set_yticks(y_pos)
    # Wrap long labels or truncate them for display
    truncated_modes = [m[:25] + "..." if len(m) > 28 else m for m in modes]
    ax.set_yticklabels(truncated_modes, fontsize=9, color='#334155')
    ax.invert_yaxis()  # top-down
    
    # Hide top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cbd5e1')
    ax.spines['bottom'].set_color('#cbd5e1')
    
    ax.set_xlabel('Occurrence Count', fontsize=10, fontweight='bold', color='#1e293b')
    ax.xaxis.grid(True, linestyle='--', alpha=0.5, color='#cbd5e1')
    ax.set_axisbelow(True)
    
    # Add values on the bars
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 0.1, bar.get_y() + bar.get_height()/2, f'{int(width)}',
                ha='left', va='center', fontsize=9, color='#334155', fontweight='bold')
                
    plt.title("Failure Mode Frequency", fontsize=11, fontweight='bold', color='#0f172a', pad=12)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf


def _clean_bold(text: str) -> str:
    """Helper to convert Markdown formatting to ReportLab XML tags."""
    # **bold** -> <b>bold</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # *italic* or _italic_ -> <i>italic</i>
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
    return text


def _build_rl_table(headers: list[str], rows: list[list[str]], styles) -> Table:
    """Builds a beautiful, wrapped, styled ReportLab table."""
    data = []
    
    # Header cells
    hdr_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )
    data.append([Paragraph(f"<b>{_clean_bold(h)}</b>", hdr_style) for h in headers])

    # Body cells
    body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155')
    )
    for row in rows:
        data.append([Paragraph(_clean_bold(cell), body_style) for cell in row])

    # 504 pt total width (612 - 2 * 54 margins)
    col_width = 504.0 / len(headers)
    t = Table(data, colWidths=[col_width] * len(headers), hAlign='LEFT')
    
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    return t


def parse_markdown_to_flowables(md_text: str) -> list:
    """Parses Markdown report text into ReportLab platypus flowables."""
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=15
    )
    h1_style = ParagraphStyle(
        'ReportH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'ReportH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0284c7'),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'ReportBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8
    )
    bullet_style = ParagraphStyle(
        'ReportBullet',
        parent=body_style,
        leftIndent=15,
        bulletIndent=5,
        spaceAfter=4
    )

    flowables = []
    lines = md_text.split('\n')

    in_table = False
    table_headers = []
    table_rows = []

    for line in lines:
        stripped = line.strip()

        # Flush table if it ends
        if in_table and (not stripped or not stripped.startswith('|')):
            if table_rows:
                flowables.append(_build_rl_table(table_headers, table_rows, styles))
                flowables.append(Spacer(1, 10))
            in_table = False
            table_headers = []
            table_rows = []

        if not stripped:
            continue

        # Header parsing
        if stripped.startswith('# '):
            flowables.append(Paragraph(stripped[2:], title_style))
            flowables.append(Spacer(1, 10))
        elif stripped.startswith('## '):
            flowables.append(Paragraph(stripped[3:], h1_style))
        elif stripped.startswith('### '):
            flowables.append(Paragraph(stripped[4:], h2_style))
        # Bullet list parsing
        elif stripped.startswith('- ') or stripped.startswith('* '):
            flowables.append(Paragraph(f"&bull; {_clean_bold(stripped[2:])}", bullet_style))
        # Table parsing
        elif stripped.startswith('|'):
            if '---' in stripped:
                continue
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if not in_table:
                table_headers = cells
                in_table = True
            else:
                table_rows.append(cells)
        # Normal paragraph parsing
        else:
            flowables.append(Paragraph(_clean_bold(stripped), body_style))

    # Flush remaining table if file ends inside a table
    if in_table and table_rows:
        flowables.append(_build_rl_table(table_headers, table_rows, styles))

    return flowables


def render_report_pdf(markdown_text: str, failure_data: list[dict]) -> bytes:
    """Takes report markdown and raw failure data, generates a plot,
    and returns compiled PDF bytes.
    """
    flowables = parse_markdown_to_flowables(markdown_text)

    # Generate and append failure history chart if data is available
    chart_buf = generate_failure_chart(failure_data)
    if chart_buf:
        # Create a visual chart container/separator
        chart_flowables = [
            Spacer(1, 10),
            Paragraph("<b>Diagnostic Chart — Failure Frequencies</b>", ParagraphStyle(
                'ChartTitle',
                fontName='Helvetica-Bold',
                fontSize=11,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=5
            )),
            Image(chart_buf, width=320, height=150, hAlign='CENTER'),
            Spacer(1, 10)
        ]
        
        # Try to insert it after the Failure History section or at the end
        inserted = False
        for idx, f in enumerate(flowables):
            if isinstance(f, Paragraph) and "Failure History" in f.text:
                # Insert a few paragraphs/tables after
                insert_pos = idx + 1
                # Find the end of table or paragraph of failure history
                while insert_pos < len(flowables) and not (
                    isinstance(flowables[insert_pos], Paragraph) and 
                    flowables[insert_pos].style.name in ('ReportH1', 'ReportTitle')
                ):
                    insert_pos += 1
                
                for item in reversed(chart_flowables):
                    flowables.insert(insert_pos, item)
                inserted = True
                break
        
        if not inserted:
            flowables.extend(chart_flowables)

    # Document assembly
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=54,   # 0.75 in
        rightMargin=54,
        topMargin=72,    # 1.0 in margin to prevent collision with header
        bottomMargin=72
    )

    doc.build(flowables, canvasmaker=NumberedCanvas)
    
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes
