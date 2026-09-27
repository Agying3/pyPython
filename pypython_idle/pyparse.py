"""Define partial Python code Parser used by editor and hyperparser.

Instances of ParseMap are used with str.translate.

The following bound search and match functions are defined:
_synchre - start of popular statement;
_junkre - whitespace or comment line;
_match_stringre: string, possibly without closer;
_itemre - line that may have bracket structure start;
_closere - line that must be followed by dedent.
_chew_ordinaryre - non-special characters.
"""
import re

# Reason last statement is continued (or C_NONE if it's not).
(C_NONE, C_BACKSLASH, C_STRING_FIRST_LINE,
 C_STRING_NEXT_LINES, C_BRACKET) = range(5)

# Find what looks like the start of a popular statement.

_synchre = re.compile(r"""
    ^
    [ \t]*
    (?: while
    |   else
    |   def
    |   return
    |   assert
    |   break
    |   class
    |   continue
    |   elif
    |   try
    |   except
    |   raise
    |   import
    |   yield
    )
    \b
""", re.VERBOSE | re.MULTILINE).search

# Match blank line or non-indenting comment line.

_junkre = re.compile(r"""
    [ \t]*
    (?: \# \S .* )?
    \n
""", re.VERBOSE).match

# Match any flavor of string; the terminating quote is optional
# so that we're robust in the face of incomplete program text.

_match_stringre = re.compile(r"""
    \""" [^"\\]* (?:
                     (?: \\. | "(?!"") )
                     [^"\\]*
                 )*
    (?: \""" )?

|   " [^"\\\n]* (?: \\. [^"\\\n]* )* "?

|   ''' [^'\\]* (?:
                   (?: \\. | '(?!'') )
                   [^'\\]*
                )*
    (?: ''' )?

|   ' [^'\\\n]* (?: \\. [^'\\\n]* )* '?
""", re.VERBOSE | re.DOTALL).match

# Match a line that starts with something interesting;
# used to find the first item of a bracket structure.

_itemre = re.compile(r"""
    [ \t]*
    [^\s#\\]    # if we match, m.end()-1 is the interesting char
""", re.VERBOSE).match

# # [pyPython 改造] pyPython 里"能开启一个缩进块"的行首关键字。
# 只有 if 和 else —— 没有 for/while/def/class/try/with。
# 约束：改语言时这里要同步，且与 colorizer/autocomplete/calltip
# 里的关键字表保持一致（四处独立维护是刻意的，见 ADR-0004）。
PYPYTHON_BLOCK_OPENERS = frozenset({"if", "else"})

# Match start of statements that should be followed by a dedent.
#
# # [pyPython 改造] 原版匹配 Python 的"块结束语句"：
#     return | break | continue | raise | pass
# pyPython **一个都没有**：
#   · 没有函数，所以没有 return；
#   · 没有循环，所以没有 break / continue；
#   · 没有异常语法，所以没有 raise；
#   · pass 也没设计。
#
# 因此这个"块结束语句"的概念在本语言里是空的，正则永不匹配。
# 保留名字 `_closere` 是因为 is_block_closer() 还在引用它——
# 而 is_block_closer() 的语义在 pyPython 里退化成"永远返回 False"
# （没有语句会强制后面的 dedent）。
#
# 约束：将来 pyPython 加了循环（while）之后，如果那时有了 break，
# 这里要把 break 加回来，否则自动缩进会在 break 之后算错块结构。
_closere = re.compile(r"""
    (?!)
""", re.VERBOSE).match

# Chew up non-special chars as quickly as possible.  If match is
# successful, m.end() less 1 is the index of the last boring char
# matched.  If match is unsuccessful, the string starts with an
# interesting char.

# # [pyPython 改造] 这个正则在"啃掉普通字符"。
# 排除集里的字符会被留下来单独处理，其余一次性跳过。
# pyPython 的 「」 必须加进排除集——否则它们会被当成普通字符啃掉，
# 后面那段 `if ch in "([{"` 根本执行不到。
#
# 这是同一处修改的**第二半**：光把 「」 加进 if 判定还不够，
# 还得让这个正则"在 「」 前面停下来"。
# 只改一处的话现象是"括号判定代码写了但从不执行"——不报错、不生效。
_chew_ordinaryre = re.compile(r"""
    [^[\](){}\u300c\u300d#'"\\]+
""", re.VERBOSE).match


class ParseMap(dict):
    r"""Dict subclass that maps anything not in dict to 'x'.

    This is designed to be used with str.translate in study1.
    Anything not specifically mapped otherwise becomes 'x'.
    Example: replace everything except whitespace with 'x'.

    >>> keepwhite = ParseMap((ord(c), ord(c)) for c in ' \t\n\r')
    >>> "a + b\tc\nd".translate(keepwhite)
    'x x x\tx\nx'
    """
    # Calling this triples access time; see bpo-32940
    def __missing__(self, key):
        return 120  # ord('x')


# Map all ascii to 120 to avoid __missing__ call, then replace some.
trans = ParseMap.fromkeys(range(128), 120)
trans.update((ord(c), ord('(')) for c in "({[")  # open brackets => '(';
trans.update((ord(c), ord(')')) for c in ")}]")  # close brackets => ')'.
trans.update((ord(c), ord(c)) for c in "\"'\\\n#")  # Keep these.
# # [pyPython 改造] pyPython 的赋值括号 「」 也要当括号处理。
#
# 为什么必须加：`「」` 里的内容**可以跨行**（见 pypython.py 的
# Lexer.tokenize —— 「」内的换行不断句）。这正是 pyparse 里
# "括号内不重新计算缩进"那条规则要处理的情况。
# 不加的话，用户在「」里换行时自动缩进会算错。
#
# 注意 「」 的码位 > 127，所以上面 ParseMap.fromkeys(range(128)) 覆盖不到，
# 不加这两行就会走 __missing__ 返回 120（当成普通字符）。
# **已验证**（见 _tmp_test_indent.py）。
trans.update((ord(c), ord('(')) for c in "\u300c")   # 「 左括号
trans.update((ord(c), ord(')')) for c in "\u300d")   # 」 右括号


class Parser:

    def __init__(self, indentwidth, tabwidth):
        self.indentwidth = indentwidth
        self.tabwidth = tabwidth

    def set_code(self, s):
        assert len(s) == 0 or s[-1] == '\n'
        self.code = s
        self.study_level = 0

    def find_good_parse_start(self, is_char_in_string):
        """
        Return index of a good place to begin parsing, as close to the
        end of the string as possible.  This will be the start of some
        popular stmt like "if" or "def".  Return None if none found:
        the caller should pass more prior context then, if possible, or
        if not (the entire program text up until the point of interest
        has already been tried) pass 0 to set_lo().

        This will be reliable iff given a reliable is_char_in_string()
        function, meaning that when it says "no", it's absolutely
        guaranteed that the char is not in a string.
        """
        code, pos = self.code, None

        # Peek back from the end for a good place to start,
        # but don't try too often; pos will be left None, or
        # bumped to a legitimate synch point.
        limit = len(code)
        for tries in range(5):
            i = code.rfind(":\n", 0, limit)
            if i < 0:
                break
            i = code.rfind('\n', 0, i) + 1  # start of colon line (-1+1=0)
            m = _synchre(code, i, limit)
            if m and not is_char_in_string(m.start()):
                pos = m.start()
                break
            limit = i
        if pos is None:
            # Nothing looks like a block-opener, or stuff does
            # but is_char_in_string keeps returning true; most likely
            # we're in or near a giant string, the colorizer hasn't
            # caught up enough to be helpful, or there simply *aren't*
            # any interesting stmts.  In any of these cases we're
            # going to have to parse the whole thing to be sure, so
            # give it one last try from the start, but stop wasting
            # time here regardless of the outcome.
            m = _synchre(code)
            if m and not is_char_in_string(m.start()):
                pos = m.start()
            return pos

        # Peeking back worked; look forward until _synchre no longer
        # matches.
        i = pos + 1
        while m := _synchre(code, i):
            s, i = m.span()
            if not is_char_in_string(s):
                pos = s
        return pos

    def set_lo(self, lo):
        """ Throw away the start of the string.

        Intended to be called with the result of find_good_parse_start().
        """
        assert lo == 0 or self.code[lo-1] == '\n'
        if lo > 0:
            self.code = self.code[lo:]

    def _study1(self):
        """Find the line numbers of non-continuation lines.

        As quickly as humanly possible <wink>, find the line numbers (0-
        based) of the non-continuation lines.
        Creates self.{goodlines, continuation}.
        """
        if self.study_level >= 1:
            return
        self.study_level = 1

        # Map all uninteresting characters to "x", all open brackets
        # to "(", all close brackets to ")", then collapse runs of
        # uninteresting characters.  This can cut the number of chars
        # by a factor of 10-40, and so greatly speed the following loop.
        code = self.code
        code = code.translate(trans)
        code = code.replace('xxxxxxxx', 'x')
        code = code.replace('xxxx', 'x')
        code = code.replace('xx', 'x')
        code = code.replace('xx', 'x')
        code = code.replace('\nx', '\n')
        # Replacing x\n with \n would be incorrect because
        # x may be preceded by a backslash.

        # March over the squashed version of the program, accumulating
        # the line numbers of non-continued stmts, and determining
        # whether & why the last stmt is a continuation.
        continuation = C_NONE
        level = lno = 0     # level is nesting level; lno is line number
        self.goodlines = goodlines = [0]
        push_good = goodlines.append
        i, n = 0, len(code)
        while i < n:
            ch = code[i]
            i = i+1

            # cases are checked in decreasing order of frequency
            if ch == 'x':
                continue

            if ch == '\n':
                lno = lno + 1
                if level == 0:
                    push_good(lno)
                    # else we're in an unclosed bracket structure
                continue

            if ch == '(':
                level = level + 1
                continue

            if ch == ')':
                if level:
                    level = level - 1
                    # else the program is invalid, but we can't complain
                continue

            if ch == '"' or ch == "'":
                # consume the string
                quote = ch
                if code[i-1:i+2] == quote * 3:
                    quote = quote * 3
                firstlno = lno
                w = len(quote) - 1
                i = i+w
                while i < n:
                    ch = code[i]
                    i = i+1

                    if ch == 'x':
                        continue

                    if code[i-1:i+w] == quote:
                        i = i+w
                        break

                    if ch == '\n':
                        lno = lno + 1
                        if w == 0:
                            # unterminated single-quoted string
                            if level == 0:
                                push_good(lno)
                            break
                        continue

                    if ch == '\\':
                        assert i < n
                        if code[i] == '\n':
                            lno = lno + 1
                        i = i+1
                        continue

                    # else comment char or paren inside string

                else:
                    # didn't break out of the loop, so we're still
                    # inside a string
                    if (lno - 1) == firstlno:
                        # before the previous \n in code, we were in the first
                        # line of the string
                        continuation = C_STRING_FIRST_LINE
                    else:
                        continuation = C_STRING_NEXT_LINES
                continue    # with outer loop

            if ch == '#':
                # consume the comment
                i = code.find('\n', i)
                assert i >= 0
                continue

            assert ch == '\\'
            assert i < n
            if code[i] == '\n':
                lno = lno + 1
                if i+1 == n:
                    continuation = C_BACKSLASH
            i = i+1

        # The last stmt may be continued for all 3 reasons.
        # String continuation takes precedence over bracket
        # continuation, which beats backslash continuation.
        if (continuation != C_STRING_FIRST_LINE
            and continuation != C_STRING_NEXT_LINES and level > 0):
            continuation = C_BRACKET
        self.continuation = continuation

        # Push the final line number as a sentinel value, regardless of
        # whether it's continued.
        assert (continuation == C_NONE) == (goodlines[-1] == lno)
        if goodlines[-1] != lno:
            push_good(lno)

    def get_continuation_type(self):
        self._study1()
        return self.continuation

    def _study2(self):
        """
        study1 was sufficient to determine the continuation status,
        but doing more requires looking at every character.  study2
        does this for the last interesting statement in the block.
        Creates:
            self.stmt_start, stmt_end
                slice indices of last interesting stmt
            self.stmt_bracketing
                the bracketing structure of the last interesting stmt; for
                example, for the statement "say(boo) or die",
                stmt_bracketing will be ((0, 0), (0, 1), (2, 0), (2, 1),
                (4, 0)). Strings and comments are treated as brackets, for
                the matter.
            self.lastch
                last interesting character before optional trailing comment
            self.lastopenbracketpos
                if continuation is C_BRACKET, index of last open bracket
        """
        if self.study_level >= 2:
            return
        self._study1()
        self.study_level = 2

        # Set p and q to slice indices of last interesting stmt.
        code, goodlines = self.code, self.goodlines
        i = len(goodlines) - 1  # Index of newest line.
        p = len(code)  # End of goodlines[i]
        while i:
            assert p
            # Make p be the index of the stmt at line number goodlines[i].
            # Move p back to the stmt at line number goodlines[i-1].
            q = p
            for nothing in range(goodlines[i-1], goodlines[i]):
                # tricky: sets p to 0 if no preceding newline
                p = code.rfind('\n', 0, p-1) + 1
            # The stmt code[p:q] isn't a continuation, but may be blank
            # or a non-indenting comment line.
            if  _junkre(code, p):
                i = i-1
            else:
                break
        if i == 0:
            # nothing but junk!
            assert p == 0
            q = p
        self.stmt_start, self.stmt_end = p, q

        # Analyze this stmt, to find the last open bracket (if any)
        # and last interesting character (if any).
        lastch = ""
        stack = []  # stack of open bracket indices
        push_stack = stack.append
        bracketing = [(p, 0)]
        while p < q:
            # suck up all except ()[]{}'"#\\
            m = _chew_ordinaryre(code, p, q)
            if m:
                # we skipped at least one boring char
                newp = m.end()
                # back up over totally boring whitespace
                i = newp - 1    # index of last boring char
                while i >= p and code[i] in " \t\n":
                    i = i-1
                if i >= p:
                    lastch = code[i]
                p = newp
                if p >= q:
                    break

            ch = code[p]

            # # [pyPython 改造] 这里原本是 `if ch in "([{"` —— 字面量比较，
            # **不查 trans 表**。
            #
            # 我第一版改错了地方：只往 trans 表里加了 「」 的映射，
            # 以为括号识别会走那张表。实测 stmt_bracketing 里 「」 完全没出现
            # （圆括号那组有 3 个 entry，「」 那组只有 1 个），
            # 才回来读这段代码发现真正判定在这里。
            #
            # 这是本项目第三次犯同一类错（见 #I11/#I12/#I14）：
            # **改了一个看起来该改的名字，而真正被读的是另一个。**
            #
            # 修法：把 「」 加进这两处的字面量集合。
            # **已验证**（_tmp_test_indent.py 里 「」 跨行会产出
            # bracketing 条目，未闭合时返回 C_BRACKET）。
            if ch in "([{\u300c":
                push_stack(p)
                bracketing.append((p, len(stack)))
                lastch = ch
                p = p+1
                continue

            if ch in ")]}\u300d":
                if stack:
                    del stack[-1]
                lastch = ch
                p = p+1
                bracketing.append((p, len(stack)))
                continue

            if ch == '"' or ch == "'":
                # consume string
                # Note that study1 did this with a Python loop, but
                # we use a regexp here; the reason is speed in both
                # cases; the string may be huge, but study1 pre-squashed
                # strings to a couple of characters per line.  study1
                # also needed to keep track of newlines, and we don't
                # have to.
                bracketing.append((p, len(stack)+1))
                lastch = ch
                p = _match_stringre(code, p, q).end()
                bracketing.append((p, len(stack)))
                continue

            if ch == '#':
                # consume comment and trailing newline
                bracketing.append((p, len(stack)+1))
                p = code.find('\n', p, q) + 1
                assert p > 0
                bracketing.append((p, len(stack)))
                continue

            assert ch == '\\'
            p = p+1     # beyond backslash
            assert p < q
            if code[p] != '\n':
                # the program is invalid, but can't complain
                lastch = ch + code[p]
            p = p+1     # beyond escaped char

        # end while p < q:

        self.lastch = lastch
        self.lastopenbracketpos = stack[-1] if stack else None
        self.stmt_bracketing = tuple(bracketing)

    def compute_bracket_indent(self):
        """Return number of spaces the next line should be indented.

        Line continuation must be C_BRACKET.
        """
        self._study2()
        assert self.continuation == C_BRACKET
        j = self.lastopenbracketpos
        code = self.code
        n = len(code)
        origi = i = code.rfind('\n', 0, j) + 1
        j = j+1     # one beyond open bracket
        # find first list item; set i to start of its line
        while j < n:
            m = _itemre(code, j)
            if m:
                j = m.end() - 1     # index of first interesting char
                extra = 0
                break
            else:
                # this line is junk; advance to next line
                i = j = code.find('\n', j) + 1
        else:
            # nothing interesting follows the bracket;
            # reproduce the bracket line's indentation + a level
            j = i = origi
            while code[j] in " \t":
                j = j+1
            extra = self.indentwidth
        return len(code[i:j].expandtabs(self.tabwidth)) + extra

    def get_num_lines_in_stmt(self):
        """Return number of physical lines in last stmt.

        The statement doesn't have to be an interesting statement.  This is
        intended to be called when continuation is C_BACKSLASH.
        """
        self._study1()
        goodlines = self.goodlines
        return goodlines[-1] - goodlines[-2]

    def compute_backslash_indent(self):
        """Return number of spaces the next line should be indented.

        Line continuation must be C_BACKSLASH.  Also assume that the new
        line is the first one following the initial line of the stmt.
        """
        self._study2()
        assert self.continuation == C_BACKSLASH
        code = self.code
        i = self.stmt_start
        while code[i] in " \t":
            i = i+1
        startpos = i

        # See whether the initial line starts an assignment stmt; i.e.,
        # look for an = operator
        endpos = code.find('\n', startpos) + 1
        found = level = 0
        while i < endpos:
            ch = code[i]
            if ch in "([{":
                level = level + 1
                i = i+1
            elif ch in ")]}":
                if level:
                    level = level - 1
                i = i+1
            elif ch == '"' or ch == "'":
                i = _match_stringre(code, i, endpos).end()
            elif ch == '#':
                # This line is unreachable because the # makes a comment of
                # everything after it.
                break
            elif level == 0 and ch == '=' and \
                   (i == 0 or code[i-1] not in "=<>!") and \
                   code[i+1] != '=':
                found = 1
                break
            else:
                i = i+1

        if found:
            # found a legit =, but it may be the last interesting
            # thing on the line
            i = i+1     # move beyond the =
            found = re.match(r"\s*\\", code[i:endpos]) is None

        if not found:
            # oh well ... settle for moving beyond the first chunk
            # of non-whitespace chars
            i = startpos
            while code[i] not in " \t\n":
                i = i+1

        return len(code[self.stmt_start:i].expandtabs(\
                                     self.tabwidth)) + 1

    def get_base_indent_string(self):
        """Return the leading whitespace on the initial line of the last
        interesting stmt.
        """
        self._study2()
        i, n = self.stmt_start, self.stmt_end
        j = i
        code = self.code
        while j < n and code[j] in " \t":
            j = j + 1
        return code[i:j]

    def is_block_opener(self):
        """Return True if the last interesting statement opens a block.

        # [pyPython 改造] 原实现是 `return self.lastch == ':'`——
        判定依据是"这行以冒号结尾"，因为 Python 的块开启一定是 `if x:`。

        pyPython **没有冒号**，块开启靠的是**行首关键字**：
            if x ~ 1
                $(42)
            else
                $(0)

        所以改成看这一行的第一个词是不是 if / else。
        **已验证**（见 _tmp_test_indent.py）。

        约束：这里必须能处理"行尾有行内注释"的情况，比如
            if x ~ 1   # 判断
        原版靠 lastch 也会在这里出错（lastch 是 '断' 不是 ':'），
        所以改用"取行首第一个词"反而更稳。
        """
        self._study2()
        i, n = self.stmt_start, self.stmt_end
        code = self.code
        # 跳过前导空白
        while i < n and code[i] in " \t":
            i = i + 1
        # 取第一个词
        j = i
        while j < n and (code[j].isalnum() or code[j] == "_"):
            j = j + 1
        word = code[i:j]
        return word in PYPYTHON_BLOCK_OPENERS

    def is_block_closer(self):
        "Return True if the last interesting statement closes a block."
        self._study2()
        return _closere(self.code, self.stmt_start) is not None

    def get_last_stmt_bracketing(self):
        """Return bracketing structure of the last interesting statement.

        The returned tuple is in the format defined in _study2().
        """
        self._study2()
        return self.stmt_bracketing


if __name__ == '__main__':
    from unittest import main
    main('idlelib.idle_test.test_pyparse', verbosity=2)
