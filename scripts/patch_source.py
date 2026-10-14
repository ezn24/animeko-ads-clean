"""Apply no-ad changes using Kotlin code tokens, independent of diff context."""
import argparse
from pathlib import Path
import re


class CompatibilityError(RuntimeError):
    pass


def tokens(source):
    # Exclude comments and literals while preserving token offsets in the source.
    result = []
    i = 0
    while i < len(source):
        if source.startswith('//', i):
            end = source.find('\n', i)
            i = len(source) if end < 0 else end
        elif source.startswith('/*', i):
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith('/*', i):
                    depth += 1
                    i += 2
                elif source.startswith('*/', i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise CompatibilityError('Unclosed Kotlin comment')
        elif source.startswith('"""', i):
            end = source.find('"""', i + 3)
            if end < 0:
                raise CompatibilityError('Unclosed Kotlin raw string')
            i = end + 3
        elif source[i] in '\"\'':
            quote = source[i]
            i += 1
            while i < len(source):
                if source[i] == '\\':
                    i += 2
                elif source[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise CompatibilityError('Unclosed Kotlin literal')
        elif source[i].isspace():
            i += 1
        else:
            match = re.match(r'[A-Za-z_$][\w$]*|\d+|\?:|==|&&|[^\s]', source[i:])
            result.append((match[0], i, i + len(match[0])))
            i += len(match[0])
    return result


def matching(ts, start, opening, closing):
    depth = 0
    for i in range(start, len(ts)):
        if ts[i][0] == opening:
            depth += 1
        elif ts[i][0] == closing:
            depth -= 1
            if depth == 0:
                return i
    raise CompatibilityError('Unbalanced Kotlin delimiters')


def method(source, class_name, method_name):
    ts = tokens(source)
    values = [t[0] for t in ts]
    classes = [i for i in range(len(ts) - 1)
               if values[i:i+2] == ['class', class_name]]
    if len(classes) != 1:
        raise CompatibilityError(f'Expected one class {class_name}, found {len(classes)}')
    start = classes[0] + 2
    # Skip constructor arguments before looking for the class body.
    while start < len(ts) and values[start] != '{':
        if values[start] == '(':
            start = matching(ts, start, '(', ')')
        start += 1
    end = matching(ts, start, '{', '}')
    methods = [i for i in range(start + 1, end - 1)
               if values[i:i+3] == ['fun', method_name, '(']]
    if len(methods) != 1:
        raise CompatibilityError(f'Expected one {class_name}.{method_name}, found {len(methods)}')
    body = matching(ts, methods[0] + 2, '(', ')') + 1
    while body < end and values[body] not in ['{', '=']:
        body += 1
    if body >= end or values[body] != '{':
        raise CompatibilityError(f'{method_name} no longer has a supported block body')
    finish = matching(ts, body, '{', '}')
    return ts, body, finish


FILTER = '.filter { it.uri == null && (it.subjectId ?: 0) > 0 }'
GUARD = 'if (true) return null // noad: disable official updater'


def recommendation(source):
    ts, begin, end = method(source, 'GetSubjectRecommendationUseCaseImpl', 'invoke')
    values = [t[0] for t in ts]
    call = ['return', 'service', '.', 'getSubjectRecommendations', '(']
    calls = [i for i in range(begin + 1, end) if values[i:i+5] == call]
    if len(calls) != 1:
        raise CompatibilityError('Recommendation return pipeline changed; no files modified')
    close = matching(ts, calls[0] + 4, '(', ')')
    filter_values = [t[0] for t in tokens(FILTER)]
    if values[close+1:close+1+len(filter_values)] == filter_values:
        return source
    if values[close+1:close+4] != ['.', 'map', '{']:
        raise CompatibilityError('Recommendation mapping changed; no files modified')
    position = ts[close][2]
    return source[:position] + FILTER + source[position:]


def updater(source):
    ts, begin, _ = method(source, 'UpdateChecker', 'checkLatestVersion')
    guard_values = [t[0] for t in tokens(GUARD)]
    if [t[0] for t in ts[begin+1:begin+1+len(guard_values)]] == guard_values:
        return source
    position = ts[begin][2]
    return source[:position] + '\n        ' + GUARD + '\n' + source[position:]


def apply(source_root, check=False):
    changes = []
    for class_name, transform in [('GetSubjectRecommendationUseCaseImpl', recommendation),
                                  ('UpdateChecker', updater)]:
        # Limit discovery to common Kotlin production sources, excluding tests.
        candidates = []
        for path in source_root.glob('app/**/src/commonMain/kotlin/**/*.kt'):
            original = path.read_text(encoding='utf-8')
            if re.search(r'\b' + class_name + r'\b', original):
                ts = tokens(original)
                values = [t[0] for t in ts]
                if any(values[i:i+2] == ['class', class_name] for i in range(len(ts) - 1)):
                    candidates.append((path, original))
        if len(candidates) != 1:
            raise CompatibilityError(f'Expected one production {class_name}, found {len(candidates)}')
        path, original = candidates[0]
        changes.append((path, original, transform(original)))
    # Validate both transformations before writing either source file.
    for path, original, modified in changes:
        if modified != original and not check:
            path.write_text(modified, encoding='utf-8', newline='\n')
        print(f'{"Checked" if check else "Patched"}: {path.relative_to(source_root)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate compatibility without writing files')
    args = parser.parse_args()
    try:
        apply(args.source, check=args.check)
    except CompatibilityError as error:
        parser.exit(1, f'No-ad compatibility check failed: {error}\n')
