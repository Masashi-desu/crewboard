"""CommonMark display only. Source strings are never rewritten or fetched."""
from html import escape
from markdown_it import MarkdownIt

renderer = MarkdownIt("commonmark", {"html": False, "breaks": True})


def image_as_text(tokens, idx, options, env):
    # Avoid automatic requests to URLs embedded in imported Markdown.
    return escape(tokens[idx].content)


renderer.renderer.rules["image"] = image_as_text


def render(text):
    return renderer.render(text)
