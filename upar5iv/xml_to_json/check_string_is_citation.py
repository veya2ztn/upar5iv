import re

# def find_citation_names(text):
#     # This pattern matches names in the format "Lastname, I." as well as "I. Lastname"
#     # It supports compound last names with hyphens and Unicode characters
#     # It also correctly handles the optional comma and space after a lastname
#     name_pattern = re.compile(r"""
#         (?:(?:\b[A-Z][a-z'-]+\b,\s)?(?:[A-Z]\.\s*)+)?   # Matches names with initials after the Lastname, e.g., "Horodecki, P."
#         (?:\b[A-Z][a-z'-]+\b)?                           # Optionally matches a Lastname if not already matched at the beginning
#     """, re.VERBOSE | re.UNICODE)

#     # Find all matches in the text
#     matches = name_pattern.findall(text)

#     # Filter out empty strings and strip whitespace
#     return [match.strip() for match in matches if match.strip()]

def find_citation_names(text):
    # This pattern matches a single initial followed by a full last name
    # It can also match a pattern of multiple initials representing first and middle names, followed by a full last name
    # It supports compound last names with hyphens
    name_pattern = re.compile(r"""
    \b # Word boundary to ensure we're matching full words
    (?:[A-Z].?\s+)+ # One or more initials with optional periods followed by spaces
    [A-Z][a-z]+ # Matches the last name starting with an uppercase letter followed by lowercase letters
    (?:\s?-?\s?[A-Z][a-z]+)* # Matches compound last names with optional spaces and hyphens
    \b # Word boundary to ensure we're matching full words
    """, re.VERBOSE)
    # Find all matches in the text
    return name_pattern.findall(text)

def has_four_digit_year(sentence):
    # Regular expression pattern to match a four-digit number (1700-2099)
    # followed by a non-digit character or end of line
    year_pattern = re.compile(r'\b(17|18|19|20)\d{2}(\D|$)')
    # Search for the pattern in the sentence
    return bool(year_pattern.search(sentence))


def has_citation_pattern(sentence):
    # Regular expression patterns to match common citation patterns
    # APA style: (Author, Year)
    apa_pattern = re.compile(r'\([\w\s]+, \d{4}\)')
    # MLA style: (Author Page)
    mla_pattern = re.compile(r'\([\w\s]+ \d+\)')
    # Chicago style: (Year, Author)
    chicago_pattern = re.compile(r'\(\d{4}, [\w\s]+\)')
    # Harvard style: (Author Year)
    harvard_pattern = re.compile(r'\([\w\s]+ \d{4}\)')

    # Search for any of the patterns in the sentence
    return any(pattern.search(sentence) for pattern in [apa_pattern, mla_pattern, chicago_pattern, harvard_pattern])

def has_slash_followed_by_digits(sentence):
    # Regular expression pattern to match a slash followed by six or seven digits
    pattern = re.compile(r'/\d{6,7}\b')
    # Search for the pattern in the sentence
    return bool(pattern.search(sentence))

def should_the_string_be_regard_as_note(sentence): #### 
    # Check for citation  should_the_string_be_regard_as_note 
    if has_four_digit_year(sentence) or has_citation_pattern(sentence):
        return False
    if has_slash_followed_by_digits(sentence):
        return False
    if len(find_citation_names(sentence))>0:
        return False
    if "@" in sentence:
        return False
    if "http" in sentence:
        return False
    if "arXiv:" in sentence:
        return False
    if len(sentence.split())<10:
        return False
    return True
