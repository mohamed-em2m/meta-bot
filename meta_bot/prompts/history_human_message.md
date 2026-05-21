---
env: default
---
"conversation_history": {{ conversation_history }}

concate_user_message:{{ concate_user_message }} to classify the language on

**Main User Query**:
{{ user_query }}

**Current Time**: {{ time }}

### important note: the history is from user orignal quries and agent repsonse in english so make your predict only on user queries langauge and never care about langagueg of response of assistant .

**Processing Rules**:
- you must output lang and voice lang if the user just put a number or quetion mark use history to determine his reposne remember history conversion is orignal user query
