# Agent Guidelines: HTML Parsing

## ⚠️ CRITICAL RULE: NEVER USE REGEX TO PARSE HTML

**When parsing HTML content, ALWAYS use Python's `HTMLParser` class or a proper HTML parsing library. NEVER use regular expressions.**

### Why This Rule Exists

HTML is a structured markup language with nested elements, attributes, escaping, and edge cases that regex cannot reliably handle:

1. **Nested elements**: `<div><span>text</span></div>` - regex can't track nesting depth
2. **Attributes with special characters**: `<div class="foo bar" id="test">` - quotes and spaces break patterns
3. **Escaped content**: `&lt;` `&gt;` `&#x3C;` - regex sees different characters than the parser
4. **Comments and CDATA**: `<!-- comment -->` `<![CDATA[...]]>` - regex will match inside these
5. **Script/style tags**: Content inside `<script>` and `<style>` should be skipped entirely
6. **Malformed HTML**: Real-world HTML often has missing closing tags, extra whitespace, etc.

### The Correct Approach: HTMLParser

Use Python's built-in `HTMLParser` class (from `html.parser`):

```python
from html.parser import HTMLParser

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []
        self.in_target_tag = False
    
    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            self.in_target_tag = True
    
    def handle_endtag(self, tag):
        if tag == 'div':
            self.in_target_tag = False
    
    def handle_data(self, data):
        if self.in_target_tag:
            self.data.append(data)

# Usage
parser = MyHTMLParser()
parser.feed(html_content)
```

### State Tracking Pattern

When extracting structured data (like class guides, spell lists, etc.):

```python
class ClassDataExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.subclasses = []
        self.in_subclass_list = False
        self.in_subclass_li = False
        self.current_text = []
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # Track when we enter a subclass list
        if tag == 'ul' and 'wp-block-list' in attrs_dict.get('class', ''):
            self.in_subclass_list = True
        
        if tag == 'li' and self.in_subclass_list:
            self.in_subclass_li = True
            self.current_text = []
    
    def handle_endtag(self, tag):
        if tag == 'ul':
            self.in_subclass_list = False
        
        if tag == 'li' and self.in_subclass_li:
            self._process_subclass()
            self.in_subclass_li = False
    
    def handle_data(self, data):
        if self.in_subclass_li:
            self.current_text.append(data)
    
    def _process_subclass(self):
        text = ''.join(self.current_text).strip()
        # Process the extracted text
        pass
```

### What's Allowed

**Regex is OK for:**
- Parsing plain text content AFTER extraction
- Cleaning up extracted text (normalizing whitespace, removing specific patterns)
- Matching simple patterns in non-HTML content

**Example (cleaning extracted text):**
```python
# OK - cleaning text that's already been extracted
desc = re.sub(r'\s+', ' ', desc)  # Normalize whitespace
desc = re.sub(r'\s*\([^)]*\)\s*', ' ', desc)  # Remove citations
```

### Reference Implementation

See the existing code that follows this pattern correctly:

- `class_extractor/engines/html_parser.py` - HTML parser for class data
- `class_extractor/engines/text_parser.py` - Text parser for .txt files
- `parse_class.py` - Unified interface that selects the right parser

### Common Mistakes to Avoid

❌ **BAD - Using regex on HTML:**
```python
# This will fail on nested elements, attributes, etc.
matches = re.findall(r'<li[^>]*>(.*?)</li>', html)
```

✅ **GOOD - Using HTMLParser:**
```python
class Parser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == 'li':
            self.in_li = True
            self.current_text = []
    
    def handle_endtag(self, tag):
        if tag == 'li' and self.in_li:
            self.process(''.join(self.current_text))
            self.in_li = False
    
    def handle_data(self, data):
        if self.in_li:
            self.current_text.append(data)
```

### Summary

| Task | Tool |
|------|------|
| Parse HTML structure | `HTMLParser` class |
| Extract text from tags | `handle_data()` callback |
| Track element state | Instance variables in parser class |
| Clean extracted text | `re.sub()` on plain strings |
| Match simple patterns | `re.match()` on plain strings |

**Remember: HTML is a programming language, not text. Parse it like code, not like a string.**
