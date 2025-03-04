import re
from datetime import datetime
from io import BytesIO

from markdown import markdown
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def strip_html_tags(html_content):
    """Remove HTML tags from a string and decode HTML entities."""
    # First convert markdown to HTML
    html = markdown(html_content)
    # Remove HTML tags
    clean = re.sub("<[^<]+?>", "", html)
    # Replace common HTML entities
    clean = (
        clean.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&ldquo;", '"')
        .replace("&rdquo;", '"')
        .replace("&lsquo;", "'")
        .replace("&rsquo;", "'")
    )
    return clean


def convert_html_to_pdf_content(html_content, styles):
    # Create paragraph style with markup
    para_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontName="DejaVuSans",
        fontSize=10,
        leading=14,
        allowWidows=0,
        allowOrphans=0,
        allowMarkup=1,
    )

    # Create list style
    list_style = ParagraphStyle(
        "ListItem",
        parent=para_style,
        leftIndent=20,
        firstLineIndent=0,
        spaceBefore=3,
        spaceAfter=3,
    )

    # Handle lists first - preserve list structure
    content = html_content
    list_items = []

    # Extract lists and their items
    list_start = content.find("<ul>")
    while list_start != -1:
        list_end = content.find("</ul>", list_start)
        if list_end == -1:
            break

        # Get the list content
        list_content = content[list_start + 4 : list_end]

        # Replace the list with a marker
        content = content[:list_start] + "||LIST_MARKER||" + content[list_end + 5 :]

        # Extract list items
        items = []
        for item in list_content.split("<li>"):
            if "</li>" in item:
                items.append(item.split("</li>")[0].strip())

        list_items.append(items)
        list_start = content.find("<ul>")

    # Handle paragraphs and line breaks
    content = content.replace("\n\n", "||PARAGRAPH||")
    content = content.replace("\n", "<br/>")
    content = content.replace("<p>", "||PARAGRAPH||")
    content = content.replace("</p>", "||PARAGRAPH||")
    content = content.replace("<br>", "<br/>")

    # Handle blockquotes and headings
    content = content.replace("<blockquote>", "<i>").replace("</blockquote>", "</i>")
    for i in range(1, 7):
        content = content.replace(f"<h{i}>", "||PARAGRAPH||<b>").replace(
            f"</h{i}>", "</b>||PARAGRAPH||"
        )

    # Process paragraphs and lists
    paragraphs = []
    list_index = 0

    for paragraph in content.split("||PARAGRAPH||"):
        if paragraph.strip():
            if "||LIST_MARKER||" in paragraph:
                # Process list
                if list_index < len(list_items):
                    for item in list_items[list_index]:
                        # Convert HTML tags in list items
                        item = item.replace("<strong>", "<b>").replace(
                            "</strong>", "</b>"
                        )
                        item = item.replace("<em>", "<i>").replace("</em>", "</i>")
                        item = item.replace("<b><i>", "<i><b>").replace(
                            "</i></b>", "</b></i>"
                        )
                        # Add bullet point and proper indentation
                        p = Paragraph(f"• {item}", list_style)
                        paragraphs.append(p)
                    list_index += 1
                    paragraphs.append(Spacer(1, 6))
            else:
                # Process regular paragraph
                lines = paragraph.split("<br/>")
                formatted_lines = []
                for line in lines:
                    if line.strip():
                        line = line.replace("<strong>", "<b>").replace(
                            "</strong>", "</b>"
                        )
                        line = line.replace("<em>", "<i>").replace("</em>", "</i>")
                        line = line.replace("<b><i>", "<i><b>").replace(
                            "</i></b>", "</b></i>"
                        )
                        formatted_lines.append(line.strip())

                if formatted_lines:
                    para_text = " ".join(formatted_lines)
                    try:
                        p = Paragraph(para_text, para_style)
                        paragraphs.append(p)
                        paragraphs.append(Spacer(1, 12))
                    except Exception as e:
                        print(f"Error creating paragraph: {str(e)}")
                        print(f"Problematic text: {para_text}")
                        plain_text = (
                            para_text.replace("<b>", "")
                            .replace("</b>", "")
                            .replace("<i>", "")
                            .replace("</i>", "")
                        )
                        p = Paragraph(plain_text, para_style)
                        paragraphs.append(p)
                        paragraphs.append(Spacer(1, 12))

    return paragraphs


def create_pdf(submission_data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    # Register fonts
    pdfmetrics.registerFont(TTFont("DejaVuSans", "fonts/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "fonts/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Italic", "fonts/DejaVuSans-Oblique.ttf"))
    pdfmetrics.registerFont(
        TTFont("DejaVuSans-BoldItalic", "fonts/DejaVuSans-BoldOblique.ttf")
    )

    # Register font family with all variants
    pdfmetrics.registerFontFamily(
        "DejaVuSans",
        normal="DejaVuSans",
        bold="DejaVuSans-Bold",
        italic="DejaVuSans-Italic",
        boldItalic="DejaVuSans-BoldItalic",
    )

    # Styles with Unicode font
    styles = getSampleStyleSheet()

    # Modify existing Normal style
    styles["Normal"].fontName = "DejaVuSans"
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 14
    styles["Normal"].allowWidows = 0
    styles["Normal"].allowOrphans = 0

    # Modify existing Heading3 style
    styles["Heading3"].fontName = "DejaVuSans-Bold"
    styles["Heading3"].fontSize = 12
    styles["Heading3"].textColor = colors.HexColor("#1E40AF")

    # Add custom styles
    styles.add(
        ParagraphStyle(
            name="CustomTitle",
            parent=styles["Heading1"],
            fontSize=18,
            spaceAfter=30,
            textColor=colors.HexColor("#2563EB"),  # Blue-600 from Tailwind
            fontName="DejaVuSans-Bold",
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontSize=16,
            spaceAfter=12,
            textColor=colors.HexColor("#1E40AF"),  # Blue-800 from Tailwind
            fontName="DejaVuSans-Bold",
        )
    )

    # Modify BodyText style if it exists, otherwise add it
    if "BodyText" in styles:
        styles["BodyText"].fontName = "DejaVuSans"
        styles["BodyText"].fontSize = 10
        styles["BodyText"].leading = 14
        styles["BodyText"].allowWidows = 0
        styles["BodyText"].allowOrphans = 0
        styles["BodyText"].allowMarkup = 1  # Enable markup parsing
    else:
        styles.add(
            ParagraphStyle(
                name="BodyText",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=10,
                leading=14,
                allowWidows=0,
                allowOrphans=0,
                allowMarkup=1,  # Enable markup parsing
            )
        )

    # Add table style
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            wordWrap="CJK",  # Enable word wrapping
            allowMarkup=1,  # Enable markup parsing
        )
    )

    # Build document content
    content = []

    # Title Page

    logo = Image("static/smart_toy.png", width=250, height=250)
    content.append(logo)

    # Add a large spacer to push the title near the bottom of the page.
    # Adjust the height (500 in this example) as needed.
    content.append(Spacer(1, 200))

    content.append(Paragraph(markdown(submission_data["title"]), styles["CustomTitle"]))
    content.append(
        Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y')}", styles["Normal"]
        )
    )
    content.append(PageBreak())

    # Brief Section
    content.append(Paragraph('<a name="brief"/>Research Brief', styles["SectionTitle"]))
    brief_html = markdown(submission_data["brief"])
    brief_paragraphs = convert_html_to_pdf_content(brief_html, styles)
    content.extend(brief_paragraphs)
    content.append(Spacer(1, 20))
    content.append(PageBreak())

    # Personas Section
    content.append(Paragraph('<a name="personas"/>AI Personas', styles["SectionTitle"]))
    for persona in submission_data["personas"]:
        # Create a table for each persona with wrapped text
        persona_data = [
            [
                Paragraph("Name", styles["TableCell"]),
                Paragraph(persona["name"], styles["TableCell"]),
            ],
            [
                Paragraph("Age", styles["TableCell"]),
                Paragraph(persona["age"], styles["TableCell"]),
            ],
            [
                Paragraph("Gender", styles["TableCell"]),
                Paragraph(persona["gender"], styles["TableCell"]),
            ],
            [
                Paragraph("Income", styles["TableCell"]),
                Paragraph(persona["income"], styles["TableCell"]),
            ],
            [
                Paragraph("Education", styles["TableCell"]),
                Paragraph(persona["education"], styles["TableCell"]),
            ],
            [
                Paragraph("Personality", styles["TableCell"]),
                Paragraph(", ".join(persona["personality"]), styles["TableCell"]),
            ],
            [
                Paragraph("Background", styles["TableCell"]),
                Paragraph(persona["background"], styles["TableCell"]),
            ],
            [
                Paragraph("Interests", styles["TableCell"]),
                Paragraph(", ".join(persona["interests"]), styles["TableCell"]),
            ],
            [
                Paragraph("Communication Style", styles["TableCell"]),
                Paragraph(
                    ", ".join(persona["communication_style"]), styles["TableCell"]
                ),
            ],
            [
                Paragraph("Core Values", styles["TableCell"]),
                Paragraph(persona["core_values"], styles["TableCell"]),
            ],
            [
                Paragraph("Knowledge Domain", styles["TableCell"]),
                Paragraph(", ".join(persona["knowledge_domain"]), styles["TableCell"]),
            ],
        ]

        # Adjust column widths to better fit content
        table = Table(persona_data, colWidths=[100, 370])
        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.HexColor("#F3F4F6"),
                    ),  # Gray-100
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor("#374151"),
                    ),  # Gray-700
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),  # Align text to top
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        1,
                        colors.HexColor("#E5E7EB"),
                    ),  # Gray-200
                ]
            )
        )
        content.append(table)
        content.append(Spacer(1, 20))
    content.append(PageBreak())

    # Research Report Section
    content.append(
        Paragraph('<a name="research"/>Research Report', styles["SectionTitle"])
    )
    for title, section_content in submission_data["research_sections"].items():
        # Convert markdown to HTML
        html_content = markdown(section_content)
        print(f"\n=== Section: {title} ===")
        print("Original markdown:", section_content)
        print("Converted HTML:", html_content)

        # Add section title
        content.append(Paragraph(title, styles["Heading3"]))
        content.append(Spacer(1, 12))

        # Convert HTML to PDF content
        section_paragraphs = convert_html_to_pdf_content(html_content, styles)
        content.extend(section_paragraphs)
        content.append(Spacer(1, 12))

    # Final Report Section (if exists)
    if submission_data.get("final_report"):
        content.append(PageBreak())
        content.append(
            Paragraph('<a name="final"/>Final Report', styles["SectionTitle"])
        )
        html_report = markdown(submission_data["final_report"])
        report_paragraphs = convert_html_to_pdf_content(html_report, styles)
        content.extend(report_paragraphs)

    # Build PDF
    doc.build(content, onFirstPage=add_page_number, onLaterPages=add_page_number)

    buffer.seek(0)
    return buffer


def add_page_number(canvas, doc):
    canvas.saveState()

    # Add text logo in top right corner
    canvas.setFont("DejaVuSans-Bold", 12)
    canvas.setFillColor(colors.HexColor("#2563EB"))  # Blue-600 from Tailwind
    canvas.drawRightString(
        doc.pagesize[0] - 72,  # Right margin
        doc.pagesize[1] - 36,  # Top margin
        "Synlabs",
    )

    # Add page number at bottom
    canvas.setFont("DejaVuSans", 9)
    canvas.setFillColor(colors.black)
    canvas.drawRightString(
        doc.pagesize[0] - 72, 72 / 2, f"Page {canvas.getPageNumber()}"
    )

    # Add footer
    canvas.setFont("DejaVuSans", 8)
    canvas.drawCentredString(doc.pagesize[0] / 2, 72 / 2, "Generated by Synlabs")

    canvas.restoreState()
