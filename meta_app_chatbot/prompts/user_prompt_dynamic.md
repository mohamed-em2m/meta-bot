---
env: default
---
Today's date is: {{ date }}
User request: "{{ user_query }}"

Here is the raw scraped data to analyze:

"""
{{ scraped_data }}
"""

Extract and organize the relevant information according to the user's request.
Return up to 4 results only. Output raw plain text only.
