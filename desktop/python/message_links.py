"""Plain-text messages plus explicit, user-opened HTTP(S) source links."""
import re
from urllib.parse import urlsplit

LINK = re.compile(r'\[([^\]\n]{1,180})\]\((https?://[^\s<>()]+)\)')


def source_links(message):
    if message.get('role') != 'assistant':
        return []
    links = []
    for match in LINK.finditer(message['content']):
        title, url = match.groups()
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme in ('http', 'https') and parsed.netloc and (title, url) not in links:
            links.append((title, url))
    return links[:5]


def display_text(message):
    if message.get('role') != 'assistant':
        return message['content']
    return LINK.sub(lambda match: match.group(1), message['content'])
