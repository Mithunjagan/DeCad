"""Small non-evaluating KiCad S-expression reader/writer."""
import json
import re

class Atom(str):
    pass

TOKEN = re.compile(r'\s*("(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+)')

def parse(text):
    tokens = [m.group(1) for m in TOKEN.finditer(text)]
    stack, roots = [], []
    for token in tokens:
        if token == '(':
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif token == ')':
            if not stack:
                raise ValueError('Unexpected closing parenthesis')
            stack.pop()
        else:
            if not stack:
                raise ValueError('Token outside expression')
            stack[-1].append(json.loads(token) if token.startswith('"') else Atom(token))
    if stack or len(roots) != 1:
        raise ValueError('Unbalanced or multiple root expressions')
    return roots[0]

def dump(node, depth=0):
    if isinstance(node, Atom):
        return str(node)
    if not isinstance(node, list):
        return json.dumps(str(node), ensure_ascii=False)
    if not any(isinstance(n, list) for n in node):
        return '(' + ' '.join(dump(n) for n in node) + ')'
    parts = []
    for n in node:
        if isinstance(n, list):
            parts.append('\n' + '  ' * (depth + 1) + dump(n, depth + 1))
        else:
            parts.append((' ' if parts else '') + dump(n))
    return '(' + ''.join(parts) + '\n' + '  ' * depth + ')'

def child(node, key, default=None):
    return next((n for n in node if isinstance(n, list) and n and n[0] == key), default)

def children(node, key):
    return [n for n in node if isinstance(n, list) and n and n[0] == key]

def expr(key, *args):
    return [Atom(key), *args]

def num(value):
    return Atom(f'{value:g}')
