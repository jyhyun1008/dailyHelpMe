"""Only star-delimited bold and italic are interpreted; all other text is literal."""
import re
from html import escape

EMPHASIS = re.compile(r"(?<!\*)(\*{1,3})(?!\*)(?=\S)([^\n]*?\S)(?<!\*)\1(?!\*)")


def emphasis_html(text):
    parts, start = [], 0
    for match in EMPHASIS.finditer(text):
        parts.append(escape(text[start:match.start()]))
        content = emphasis_html(match[2])
        tags = {1: ("<i>", "</i>"), 2: ("<b>", "</b>"), 3: ("<b><i>", "</i></b>")}
        opening, closing = tags[len(match[1])]
        parts.append(opening + content + closing)
        start = match.end()
    parts.append(escape(text[start:]))
    return ''.join(parts)
