import sqlparse
from sqlparse.sql import Comparison, Parenthesis, Where
from sqlparse.tokens import Keyword, Newline, Punctuation


# 1) operator mapping
def map_operator(op):
	mapping = {
		'=': '=',
		'!=': '!=',
		'<>': '!=',
		'>': '>',
		'<': '<',
		'>=': '>=',
		'<=': '<=',
		'IN': 'in',
		'NOT IN': 'not in',
		'LIKE': 'like',
		'ILIKE': 'ilike',
	}
	return mapping.get(op.upper(), op.lower())


# 2) parse a single Comparison into [field, op, value]
def parse_comparison(comp: Comparison):
	tokens = [
		t for t in comp.tokens if not t.is_whitespace and t.ttype is not Punctuation
	]
	if len(tokens) < 3:
		return None
	field = tokens[0].value
	op = map_operator(tokens[1].value)
	raw = tokens[2].value.strip()
	if op in ('in', 'not in') and raw.startswith('(') and raw.endswith(')'):
		vals = [v.strip().strip('\'"') for v in raw[1:-1].split(',')]
		value = vals
	else:
		if raw.startswith(("'", '"')) and raw.endswith(("'", '"')):
			value = raw[1:-1]
		else:
			try:
				value = int(raw)
			except ValueError:
				try:
					value = float(raw)
				except ValueError:
					value = raw
	return [field, op, value]


# 3) flatten the WHERE clause into a list of tokens: operands (lists), 'AND'/'OR', '(' and ')'
def tokenize_where(where: Where):
	toks = [t for t in where.tokens if not t.is_whitespace and t.ttype is not Newline]
	out = []
	for t in toks:
		# skip leading WHERE keyword
		if t.ttype == Keyword and t.value.upper() == 'WHERE':
			continue
		if isinstance(t, Comparison):
			cond = parse_comparison(t)
			if cond:
				out.append(cond)
		elif t.ttype == Keyword and t.value.upper() in ('AND', 'OR'):
			out.append(t.value.upper())
		elif isinstance(t, Parenthesis):
			out.append('(')
			# recurse inside the parentheses:
			inner_where = Where(t.tokens)
			out.extend(tokenize_where(inner_where))
			out.append(')')
		# else: ignore commas, punctuation, etc.
	return out


# 4) shunting‐yard: convert mixed tokens → RPN
precedence = {'OR': 1, 'AND': 2}
assoc = {'OR': 'left', 'AND': 'left'}


def to_rpn(tokens):
	output = []
	opstack = []
	for tok in tokens:
		if isinstance(tok, list):
			# a parsed comparison
			output.append(tok)
		elif tok == '(':
			opstack.append(tok)
		elif tok == ')':
			while opstack and opstack[-1] != '(':
				output.append(opstack.pop())
			opstack.pop()  # remove '('
		elif tok in ('AND', 'OR'):
			while (
				opstack
				and opstack[-1] in precedence
				and (
					(
						assoc[tok] == 'left'
						and precedence[tok] <= precedence[opstack[-1]]
					)
					or (
						assoc[tok] == 'right'
						and precedence[tok] < precedence[opstack[-1]]
					)
				)
			):
				output.append(opstack.pop())
			opstack.append(tok)
		else:
			# ignore anything else
			pass

	while opstack:
		output.append(opstack.pop())
	return output


# 5) evaluate the RPN into a single Odoo domain list
def rpn_to_domain(rpn):
	stack = []
	for tok in rpn:
		if isinstance(tok, list):
			# single condition → push as a domain list
			stack.append([tok])
		elif tok == 'AND':
			right = stack.pop()
			left = stack.pop()
			# AND in Odoo is implicit: just concatenate
			stack.append(left + right)
		elif tok == 'OR':
			right = stack.pop()
			left = stack.pop()
			# OR in Odoo: prefix '|' before the two branches
			stack.append(['|'] + left + right)
		else:
			raise ValueError(f'Unexpected token in RPN: {tok}')
	return stack[0] if stack else []


# 6) main entrypoint
def sql_to_odoo_domain(sql: str):
	parsed = sqlparse.parse(sql)
	if not parsed:
		return []
	stmt = parsed[0]
	where = next((t for t in stmt.tokens if isinstance(t, Where)), None)
	if not where:
		return []
	flat = tokenize_where(where)
	rpn = to_rpn(flat)
	domain = rpn_to_domain(rpn)
	return domain
