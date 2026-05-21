---
env: default
---
## AGENT RESPONSE FOR AUDIO CONVERSION:
{{ response }}

## AUDIO PARAMETERS:
- Target language/dialect: {{ lang }}
- Max segments: 2
- Output format: Raw TTS-ready text
- Special instructions:
  1. Preserve ALL original facts and terms
  2. Add pronunciation aids ONLY where needed
  3. Include apartment IDs explicitly: "Apartment 1 (ID: 123)..." as Apartment 1 Num 123
Normalize the the text
## CRITICAL CONSTRAINTS:
- Every word must be TTS-pronounceable in {{ lang }}
- if main agent make his reponse in another language rather than {{ lang }} translate all his senteace to {{ lang }}.
