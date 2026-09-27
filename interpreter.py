"""一个纯 Python 实现的**解释器**（不是编译器）。

执行管线（单文件纵向分层，模块边界用注释标出，避免用包目录装这么小的程序）：

    Lexer（词法分析） --Token 列表--> Parser（语法分析） --语法树--> Interpreter（直接遍历语法树求值）

有意为之的边界（改代码前先看这里）：

  约束：这里不做字节码生成，也不做任何基于语法树的编译优化；Interpreter 每执行一个节点就
        就地求值，性能不是目标，可读性和可扩展性才是。要加优化请另开一个后端，不要在
        解释器里塞"顺便优化一下"的分支。
  约束：本文件是**最小骨架**，不是一门完整语言。没有控制流、函数、字符串/列表、
        块作用域；变量表只有全局一层（见 Interpreter.variables）。要往上长请先读
        docs/extension-design.md——那份文档给出了扩展顺序，并标明了本文件中
        哪些部分会被推翻（全局 dict、BINARY_OPS、_execute 签名）。**先照那份文档的
        顺序做，否则会返工**：函数会推翻 Environment，若先写控制流再改 Environment，
        循环体的执行路径要全部回改。
  {意图：把三种报错分开——LexError 是词法层看不懂字符，ParseError 是 token 序列不构成合法
   句子，RuntimeError 是句子合法但执行不下去（比如除零、用未定义变量）。因为三者的修复
   动作完全不同，混成一个异常会让调用方只能靠猜。}
  {意图：所有错误都携带 行号/列号 + 原始源码行。因为只报"第 3 行有错"在长表达式里几乎
   无法定位；Paser/Interp 的列号取自 token，Lexer 的列号取自当前扫描位置。}
  取舍：变量只支持动态类型（Python 的 int/float），没有声明类型检查；换来的是
        VarDecl 和 Assign 可以共用同一套求值路径。

用法：
    python interpreter.py            # 跑内置测试用例
    python -c "import interpreter; interpreter.run('x = 1; print(x)')"
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


# =====================================================================================
# 第 1 层：词法分析器（Lexer）
# =====================================================================================


# -------------------------------------------------------------------------------------
# Token 类型表
#
# 每个 token 类型的确切含义（词法层只负责"切词"，不判断句子是否合法）：
#
#   NUMBER      数字字面量。整数或小数，如 42 / 3.14。语义值在 lexeme 里，由 Parser 转 float/int。
#   IDENT       标识符。变量名，如 x / total / _tmp。是否已定义由 Interpreter 判断，不是 Lexer。
#   PRINT      关键字 print。保留字，不能当变量名。
#   TRUE/FALSE  关键字 true / false，布尔字面量。
#   PLUS/MINUS/STAR/SLASH
#               + - * / 四个算术运算符。
#   LPAREN/RPAREN
#               ( ) 圆括号，用于改变运算优先级。
#   ASSIGN      = 赋值号。注意它和将来可能的 == 是两回事，本语言没有比较运算符。
#   SEMICOLON   ; 语句分隔符。分行不是语句边界，分号（或 EOF）才是。
#   EOF        输入结束哨兵。存在的意义是让 Parser 不必到处判 None，
#              代价是词法阶段多产出这一个 token。
# -------------------------------------------------------------------------------------
TOKEN_TYPES = (
    "NUMBER",
    "IDENT",
    "PRINT",
    "TRUE",
    "FALSE",
    "PLUS",
    "MINUS",
    "STAR",
    "SLASH",
    "LPAREN",
    "RPAREN",
    "ASSIGN",
    "SEMICOLON",
    "EOF",
)

KEYWORDS = {
    "print": "PRINT",
    "true": "TRUE",
    "false": "FALSE",
}

# 单字符运算符/分隔符到 token 类型的映射。
# 本语言没有多字符运算符（没有 ==、<=、+=），所以 Lexer 不需要前瞻；一旦加入 ==，
# 就必须改成最长匹配，否则 `=` 会先把 `==` 的前半截吃掉。
# 注意：加 compare 运算符是 docs/extension-design.md 第 5.2 节的改动点，
# 它只影响本表与 Lexer，不需要动 Parser/Interpreter——这是分层带来的收益。
SINGLE_CHAR_TOKENS = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "(": "LPAREN",
    ")": "RPAREN",
    "=": "ASSIGN",
    ";": "SEMICOLON",
}


class CalcError(Exception):
    """本语言所有错误的基类，方便调用方 `except CalcError` 一把兜住三类错误。

    子类各自携带源码位置；这里只保存消息和源码行，供格式化使用。
    """

    def __init__(self, message: str, line: int, column: int, source_line: str = ""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line

    def format(self) -> str:
        """生成带位置和出错行指示符的报告，例如：

            RuntimeError: 变量 'y' 未定义（第 3 行 第 7 列）
              |   x = y + 1;
              |         ^
        """
        header = f"{type(self).__name__}: {self.message}（第 {self.line} 行 第 {self.column} 列）"
        if not self.source_line:
            return header
        # 列号是 1-based，构建指示符时要减 1；tab 已经按 4 空格展开过（见 Lexer），
        # 所以这里直接用空格对齐即可。
        caret_pad = " " * max(self.column - 1, 0)
        return f"{header}\n  | {self.source_line}\n  | {caret_pad}^"


class LexError(CalcError):
    """词法错误：出现了本语言不认识的字符，或数字字面量写法非法。"""


@dataclass(frozen=True)
class Token:
    """一个词法单元。

    lexeme 是原始文本（保真，便于报错回显）；value 是解释后的值（NUMBER 存数值，
    TRUE/FALSE 存 bool，其余为 None）。行号/列号都是 1-based，列号指向 token 第一个字符。
    """

    type: str
    lexeme: str
    line: int
    column: int
    value: Any = None

    def __repr__(self) -> str:  # 便于调试打印
        return f"Token({self.type}, {self.lexeme!r}, {self.line}:{self.column})"


class Lexer:
    """把源代码字符串切成 Token 列表。

    {意图：用显式下标 i 而不是 for 循环，因为数字扫描需要"吃掉多个字符"后回退/前进，
      for 循环的隐式游标做不到。}
    约束：输入里的 tab 一律按 4 空格展开再扫描——否则报错指示符的列对齐会在
          "源码里有 tab"和"我们画的空格"之间错位。
    """

    TAB_WIDTH = 4

    def __init__(self, source: str):
        self.raw_source = source
        # 先展开 tab，再按 \n 切成行数组：报错时直接取 source_lines[line-1]。
        self.source = source.expandtabs(self.TAB_WIDTH)
        self.source_lines = self.source.split("\n")
        self.pos = 0
        self.line = 1
        self.column = 1

    # -- 位置辅助 -------------------------------------------------------------------

    def _current_line_text(self) -> str:
        return self.source_lines[self.line - 1] if self.line - 1 < len(self.source_lines) else ""

    def _error(self, message: str) -> LexError:
        return LexError(message, self.line, self.column, self._current_line_text())

    def _peek(self, offset: int = 0) -> str:
        """看当前位置之后第 offset 个字符，越界返回空串（避免到处写边界判断）。"""
        index = self.pos + offset
        return self.source[index] if index < len(self.source) else ""

    def _advance(self) -> str:
        """吞掉一个字符并推进位置，同时维护行号/列号。"""
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    # -- 主循环 ---------------------------------------------------------------------

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.pos < len(self.source):
            char = self._peek()

            # 空白与换行只是分隔符，不产出 token。
            if char in " \t\r\n":
                self._advance()
                continue

            # 注释：`#` 到行尾。新起一行注释，避免把语言注释和 Python 注释搞混。
            if char == "#":
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._advance()
                continue

            # 数字：必须以数字开头；`.` 开头（如 .5）不合法，强制写成 0.5。
            if char.isdigit():
                tokens.append(self._scan_number())
                continue

            # 标识符/关键字：首字符不能是数字，后续可含数字和下划线。
            if char.isalpha() or char == "_":
                tokens.append(self._scan_identifier())
                continue

            # 单字符运算符与分隔符。
            if char in SINGLE_CHAR_TOKENS:
                tokens.append(
                    Token(SINGLE_CHAR_TOKENS[char], char, self.line, self.column)
                )
                self._advance()
                continue

            # 走到这里说明是不认识的字符。这里必须报错而不是跳过，
            # 否则 `1 $ 2` 会被静默解释成 `1 2`，错误被推迟到更难定位的地方。
            raise self._error(f"无法识别的字符 {char!r}")

        # 末尾补 EOF 哨兵：列号指向源码末尾之后一格。
        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    def _scan_number(self) -> Token:
        """扫描数字字面量，接受 `123` 和 `123.45` 两种形式。

        约束：只允许一个小数点；`1.2.3` 报错而不是切成 `1.2` + `.3`，
              因为后者会产生一个以 `.` 开头的诡异 token，错误信息反而更难懂。
        """
        start_line, start_column, start_pos = self.line, self.column, self.pos
        while self._peek().isdigit():
            self._advance()

        is_float = False
        if self._peek() == ".":
            is_float = True
            self._advance()
            if not self._peek().isdigit():
                # `1.` 这种写法拒绝掉：允许它会带来"小数点后必须有数字吗"的一串边界歧义。
                raise self._error("小数点后必须跟数字")
            while self._peek().isdigit():
                self._advance()

        lexeme = self.source[start_pos : self.pos]
        value: Any = float(lexeme) if is_float else int(lexeme)
        return Token("NUMBER", lexeme, start_line, start_column, value)

    def _scan_identifier(self) -> Token:
        """扫描标识符，再查关键字表决定它是 IDENT 还是 PRINT/TRUE/FALSE。"""
        start_line, start_column, start_pos = self.line, self.column, self.pos
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()

        lexeme = self.source[start_pos : self.pos]
        token_type = KEYWORDS.get(lexeme, "IDENT")
        value = True if token_type == "TRUE" else False if token_type == "FALSE" else None
        return Token(token_type, lexeme, start_line, start_column, value)


# =====================================================================================
# 第 2 层：语法分析器（Parser）
# =====================================================================================
#
# 文法（EBNF，`|` 是或，`{}` 是重复，`[]` 是可选）：
#
#   program     ::= { statement } EOF
#   statement   ::= assignment | print_stmt | expr_stmt
#   assignment  ::= IDENT "=" expression ";"
#   print_stmt  ::= "print" expression ";"
#   expr_stmt   ::= expression ";"
#   expression  ::= term { ("+" | "-") term }
#   term        ::= factor { ("*" | "/") factor }
#   factor      ::= NUMBER
#                 | "true" | "false"
#                 | IDENT
#                 | "(" expression ")"
#
# 优先级与结合性说明：
#   * `/` 绑定得比 `+` `-` 紧，靠的是 expression -> term -> factor 三层，而不是在
#     解析时算优先级表。左递归改写成循环（{ ... }），所以 `1 - 2 - 3` 自然左结合成
#     `(1-2)-3`；若写成右结合，结果会变成 2，这是很容易踩的坑。
#
#   {意图：Parser 只产出语法树，不做任何求值、常量折叠或类型检查。因为一旦在这里算
#     `2 * 3`，报错就失去了"执行期"和"语法期"的区分，调试时很难判断是谁的锅。}
#
# 语句终止约定：
#   分号是唯一的语句结束标记。最后一条语句允许省略分号（后跟 EOF），这是刻意的
#   宽容：交互式输入 `x = 1` 不带分号也能跑，而中间漏掉分号仍会报错。


class ParseError(CalcError):
    """语法错误：token 序列不构成合法语句。"""


# -------------------------------------------------------------------------------------
# 语法树节点。
#
# 只有三类节点，因为它们恰好对应"求值"这一件事的三种形态：
#   Number/Bool  —— 叶子，直接取值
#   Var          —— 叶子，查环境
#   BinOp        —— 内部节点，递归求左右再合并
# 没有为每个运算符建一个类：运算符是字符串，语义集中在 Interpreter.eval_binop 的
# 一个字典里，加运算符时只改一处。
# -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Number:
    """数字字面量节点。value 是 Python 的 int 或 float。"""

    value: Any


@dataclass(frozen=True)
class Bool:
    """布尔字面量节点（true / false）。参与算术时按 1/0 处理，见 Interpreter。"""

    value: bool


@dataclass(frozen=True)
class Var:
    """变量引用节点。name 是否已定义由 Interpreter 在运行期判断。"""

    name: str
    line: int
    column: int


@dataclass(frozen=True)
class BinOp:
    """二元运算节点。op ∈ {"+", "-", "*", "/"}，left/right 是任意表达式节点。

    line/column 取的是运算符的位置：报除零错误时，指向运算符比指向整个表达式更有用。
    """

    op: str
    left: Any
    right: Any
    line: int
    column: int


@dataclass(frozen=True)
class Assign:
    """赋值语句 `IDENT = expression`。本语言没有"声明"关键字，首次赋值即声明。"""

    name: str
    value: Any
    line: int
    column: int


@dataclass(frozen=True)
class Print:
    """print 语句，求值 value 并输出到 stdout。"""

    value: Any
    line: int
    column: int


@dataclass(frozen=True)
class ExprStmt:
    """表达式语句：只求值、不打印（`x + 1;`）。

    {意图：存在的唯一理由是让 run() 能返回"最后一条语句的值"，方便 REPL 和测试
     直接取出结果。所以它不产生任何输出——想要输出必须写 print，避免"忘记 print
     却意外看到输出"这种隐式行为。}
    """

    value: Any
    line: int
    column: int


class Parser:
    """递归下降解析器：把 Token 列表变成语句节点列表。

    {意图：用当前 token 下标 + 一个"是否已前进"的标志位来驱动，而不是经典的
     peek/advance 两函数式写法。这样才能在"解析出错时给出**上一个** token 的位置"，
     因为报错点通常是我们刚消费完的那个 token 之后。}
    """

    def __init__(self, tokens: Sequence[Token], source_lines: Sequence[str]):
        self.tokens = list(tokens)
        self.source_lines = list(source_lines)
        self.pos = 0
        self._advanced = False  # 上一次 _peek() 之后是否调用过 _advance()

    # -- token 游标 -----------------------------------------------------------------

    def _current_line_text(self) -> str:
        line = self._peek().line
        return self.source_lines[line - 1] if line - 1 < len(self.source_lines) else ""

    def _peek(self) -> Token:
        self._advanced = False
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        token = self.tokens[self.pos]
        if token.type != "EOF":
            self.pos += 1
        self._advanced = True
        return token

    def _error(self, message: str) -> ParseError:
        """在"出错的位置"构造错误。

        取上一个 token 的位置：刚消费完 IDENT 却期待 `=` 时，真正想指的就是那个 IDENT，
        而当前 token 已经跑到后面去了。
        """
        token = self.tokens[self.pos - 1] if self._advanced and self.pos > 0 else self._peek()
        return ParseError(message, token.line, token.column, self._current_line_text())

    def _check(self, token_type: str) -> bool:
        return self._peek().type == token_type

    def _match(self, token_type: str) -> bool:
        """若当前 token 类型匹配则消费并返回 True。"""
        if self._check(token_type):
            self._advance()
            return True
        return False

    def _expect(self, token_type: str, what: str) -> Token:
        """强制要求当前 token 类型；否则抛出带位置和"期待什么/实际是什么"的错误。"""
        if not self._check(token_type):
            actual = self._peek()
            found = actual.lexeme if actual.type != "EOF" else "文件结尾"
            raise self._error(f"期待{what}，却遇到 {found!r}")
        return self._advance()

    # -- 文法规则 -------------------------------------------------------------------

    def parse(self) -> list[Any]:
        """program ::= { statement } EOF"""
        statements: list[Any] = []
        while not self._check("EOF"):
            statements.append(self._statement())
        return statements

    def _statement(self) -> Any:
        """statement ::= assignment | print_stmt | expr_stmt

        assignment 和 expr_stmt 都以 IDENT 开头，靠**一个 token 的前瞻**区分：
        `IDENT` 后面跟 `=` 才是赋值，否则是表达式语句（REPL 里输入 `x;` 看值）。

        {意图：先扫描一遍 token 找到 `=`，再决定走哪条规则。因为把"合法但不赋值"
         的表达式也纳入语句后，无前瞻的写法会把 `x;` 误判成"赋值漏了 ="，报错信息
         会指向完全错误的方向。}
        约束：这个前瞻只看下一个 token，不做完整回溯；一旦将来支持 `==` 或多字符
              运算符，必须同步改这里。
        """
        if self._check("PRINT"):
            return self._print_statement()
        if self._check("IDENT") and self.tokens[self.pos + 1].type == "ASSIGN":
            return self._assignment()
        if self._check("IDENT") or self._check("NUMBER") or self._check("LPAREN") or self._check(
            "TRUE"
        ) or self._check("FALSE"):
            return self._expression_statement()
        token = self._peek()
        found = token.lexeme if token.type != "EOF" else "文件结尾"
        raise ParseError(
            f"语句必须以变量名、'print' 或表达式开头，却遇到 {found!r}",
            token.line,
            token.column,
            self._current_line_text(),
        )

    def _assignment(self) -> Assign:
        """assignment ::= IDENT "=" expression ";" """
        name_token = self._expect("IDENT", "变量名")
        # 这里不用 _expect("ASSIGN") —— 想让报错带上"是不是想写 =="这类更贴心的提示。
        if not self._check("ASSIGN"):
            token = self._peek()
            found = token.lexeme if token.type != "EOF" else "文件结尾"
            raise ParseError(
                f"变量 {name_token.lexeme!r} 之后期待 '='，却遇到 {found!r}"
                + ("（本语言没有 '=='，比较运算暂不支持）" if found == "==" else ""),
                token.line,
                token.column,
                self._current_line_text(),
            )
        self._advance()
        value = self._expression()
        self._expect_statement_end()
        return Assign(name_token.lexeme, value, name_token.line, name_token.column)

    def _print_statement(self) -> Print:
        """print_stmt ::= "print" expression ";" """
        print_token = self._expect("PRINT", "'print'")
        value = self._expression()
        self._expect_statement_end()
        return Print(value, print_token.line, print_token.column)

    def _expression_statement(self) -> ExprStmt:
        """expr_stmt ::= expression ";" """
        start_token = self._peek()
        value = self._expression()
        self._expect_statement_end()
        return ExprStmt(value, start_token.line, start_token.column)

    def _expect_statement_end(self) -> None:
        """语句结束：必须是 `;`，或者是文件结尾（最后一条语句允许省略分号）。"""
        if self._match("SEMICOLON"):
            return
        if self._check("EOF"):
            return
        token = self._peek()
        raise ParseError(
            f"语句结尾期待 ';'，却遇到 {token.lexeme!r}",
            token.line,
            token.column,
            self._current_line_text(),
        )

    def _expression(self) -> Any:
        """expression ::= term { ("+" | "-") term }  —— 加减，最低优先级，左结合。"""
        node = self._term()
        while self._check("PLUS") or self._check("MINUS"):
            op_token = self._advance()
            right = self._term()
            node = BinOp(op_token.lexeme, node, right, op_token.line, op_token.column)
        return node

    def _term(self) -> Any:
        """term ::= factor { ("*" | "/") factor }  —— 乘除，比加减紧，左结合。"""
        node = self._factor()
        while self._check("STAR") or self._check("SLASH"):
            op_token = self._advance()
            right = self._factor()
            node = BinOp(op_token.lexeme, node, right, op_token.line, op_token.column)
        return node

    def _factor(self) -> Any:
        """factor ::= NUMBER | "true" | "false" | IDENT | "(" expression ")"

        括号在这里递归回最低优先级的 expression，所以括号内的运算先算——优先级
        完全由"谁先调用谁"决定，没有单独的优先级数字表。
        """
        token = self._peek()

        if token.type == "NUMBER":
            self._advance()
            return Number(token.value)

        if token.type in ("TRUE", "FALSE"):
            self._advance()
            return Bool(token.value)

        if token.type == "IDENT":
            self._advance()
            return Var(token.lexeme, token.line, token.column)

        if token.type == "LPAREN":
            self._advance()
            inner = self._expression()
            if not self._check("RPAREN"):
                current = self._peek()
                found = current.lexeme if current.type != "EOF" else "文件结尾"
                raise ParseError(
                    f"括号没有闭合，期待 ')'，却遇到 {found!r}",
                    token.line,
                    token.column,
                    self._current_line_text(),
                )
            self._advance()
            return inner

        # 剩下的情况包括 `1 + ` 这种"表达式没写完"，以及 `print ;` 这种空表达式。
        found = token.lexeme if token.type != "EOF" else "文件结尾"
        raise ParseError(
            f"期待一个表达式（数字、变量或括号），却遇到 {found!r}",
            token.line,
            token.column,
            self._current_line_text(),
        )


# =====================================================================================
# 第 3 层：解释执行器（Interpreter）
# =====================================================================================


class CalcRuntimeError(CalcError):
    """运行期错误：语法合法但执行不下去（未定义变量、除以零、用错类型）。

    类名带 Calc 前缀是为了不和 Python 内置的 RuntimeError 混淆——否则在 except 里
    写错名字会静默捕获到内置异常，非常难查。
    """


class Interpreter:
    """直接遍历语法树求值。

    {意图：这是"解释器"和"编译器"的分界线所在——没有字节码、没有指令序列、
     没有优化 pass。tree-walking 每执行一次就在 Python 栈上递归一次，代价是慢，
     收益是每个节点的语义都能在源码里一眼找到，加新语法不需要动代码生成。}
    取捨：变量表就是一个普通 dict，作用域只有全局一层，没有闭包/块作用域。
    """

    # 运算符 -> 实现。集中放一起，是因为"加一个运算符要改哪些地方"应该是一目了然的；
    # 除以零不在这里处理，见 _eval_binop。
    #
    # 约束：这个表假设"两个数字进去、一个数字出来"，因此**加字符串/列表时必须推翻它**，
    #       否则 `1 + "a"` 会泄漏 Python 的 TypeError（错误信息里出现 int/str 这类
    #       实现层类型名，用户不该看到）。替换方案见 docs/extension-design.md 第 2 节。
    BINARY_OPS = {
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
        "/": lambda a, b: a / b,
    }

    def __init__(self, source_lines: Sequence[str], output: Any = None):
        # 约束：全局唯一的一层作用域。加函数/块作用域时要换成 Environment 链，
        #       并给 _execute/_evaluate 加上 env 参数——见 extension-design.md 第 3 节。
        #       注意测试 test_interpreter_state_survives_across_run 直接依赖这个字段。
        self.variables: dict[str, Any] = {}
        self.source_lines = list(source_lines)
        # output 是一个可注入的"写一行"函数：默认 print 到 stdout，测试时可传入
        # 列表的 append 来捕获输出，从而不必重定向 sys.stdout。
        self.output = output if output is not None else print

    def _line_text(self, line: int) -> str:
        return self.source_lines[line - 1] if line - 1 < len(self.source_lines) else ""

    def run(self, statements: Iterable[Any]) -> Any:
        """执行整个程序，把最后一条语句的值作为结果返回（None 表示无值）。

        返回值只为方便 REPL 式使用（`run('1+1;')` 得到 2）；print 语句返回 None。
        """
        result = None
        for statement in statements:
            result = self._execute(statement)
        return result

    def _execute(self, node: Any) -> Any:
        """语句级分发：print 产生输出，赋值写入变量表，表达式语句只求值。

        Assign 与 ExprStmt 都返回求值结果，这样 run() 才能把"最后一条语句的值"
        交回给调用方（REPL 语义）；Print 返回 None，因为它的可见效果是输出本身。
        """
        if isinstance(node, Assign):
            value = self._evaluate(node.value)
            self.variables[node.name] = value
            return value
        if isinstance(node, Print):
            value = self._evaluate(node.value)
            self.output(self._format_value(value))
            return None
        if isinstance(node, ExprStmt):
            return self._evaluate(node.value)
        # 到不了这里：Parser 只会产出上述三种语句。
        raise CalcRuntimeError(
            f"内部错误：未知语句节点 {type(node).__name__}", 1, 1, ""
        )

    def _evaluate(self, node: Any) -> Any:
        """表达式求值：递归下降遍历语法树，返回值本身（int/float/bool）。"""
        if isinstance(node, Number):
            return node.value

        if isinstance(node, Bool):
            # 布尔按 1/0 参与算术；显示时才还原成 true/false（见 _format_value）。
            return node.value

        if isinstance(node, Var):
            if node.name not in self.variables:
                # 这里不回显"全部已定义变量"：长程序里那串列表会淹没真正的错误信息。
                raise CalcRuntimeError(
                    f"变量 {node.name!r} 未定义（可用的变量：{self._known_names()}）",
                    node.line,
                    node.column,
                    self._line_text(node.line),
                )
            return self.variables[node.name]

        if isinstance(node, BinOp):
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            return self._eval_binop(node, left, right)

        raise CalcRuntimeError(
            f"内部错误：未知表达式节点 {type(node).__name__}", 1, 1, ""
        )

    def _eval_binop(self, node: BinOp, left: Any, right: Any) -> Any:
        """执行一次二元运算。

        除零处理说明：Python 的 `/` 对 0 会抛 ZeroDivisionError，但那个异常没有行号，
        所以在这里提前拦下，换成带位置的 CalcRuntimeError。
        """
        if node.op == "/" and right == 0:
            raise CalcRuntimeError(
                "除以零", node.line, node.column, self._line_text(node.line)
            )
        try:
            return self.BINARY_OPS[node.op](left, right)
        except TypeError as exc:
            # 例如 true + "字符串"（本语言暂时没有字符串，但保留这条兜底路径给未来扩展）。
            raise CalcRuntimeError(
                f"运算符 {node.op!r} 不支持 {self._type_name(left)} 与 "
                f"{self._type_name(right)} 的运算",
                node.line,
                node.column,
                self._line_text(node.line),
            ) from exc

    def _known_names(self) -> str:
        names = "、".join(sorted(self.variables))
        return names if names else "无"

    @staticmethod
    def _type_name(value: Any) -> str:
        return type(value).__name__

    @staticmethod
    def _format_value(value: Any) -> str:
        """输出格式：bool 显示 true/false；float 若是整数值则去掉多余小数（4.0 -> 4）。

        取舍：`6 / 3` 显示成 2 而不是 2.0。这与 Python 相冲突，但本语言只有数字一种
              数值类型，用户写 `6 / 3` 时期待的是 2；要用 Python 语义的调用方
              应该直接用 _evaluate 拿原始值。
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            if math.isfinite(value) and value.is_integer():
                return str(int(value))
            return repr(value)
        return str(value)


# =====================================================================================
# 便捷入口
# =====================================================================================


def run(source: str, output: Any = None) -> Any:
    """一行式入口：源码字符串 -> 执行结果。

    output 可注入（例如 list 的 append）以捕获 print 输出；异常统一是 CalcError 子类，
    调用方用 `except CalcError as e: print(e.format())` 就能拿到带位置的报告。

    三条管线在这里串起来：tokens = Lexer 的产物，statements = Parser 的产物，
    Interpreter 只消费 statements 并直接遍历执行。
    """
    lexer = Lexer(source)
    tokens = lexer.tokenize()  # 可能抛 LexError
    parser = Parser(tokens, lexer.source_lines)
    statements = parser.parse()  # 可能抛 ParseError
    interpreter = Interpreter(lexer.source_lines, output)
    return interpreter.run(statements)  # 可能抛 CalcRuntimeError


def main() -> int:
    """跑几个演示用例。返回进程退出码：0 表示全部符合预期。"""
    print("=" * 72)
    print("演示 1：变量、四则运算、print")
    print("=" * 72)
    demo_source = """\
# 本语言用 # 开始注释，用 ; 结束语句
x = 10;
y = 3;
print x + y;          # 13
print x - y;          # 7
print x * y;          # 30
print x / y;          # 3.3333333333333335（浮点除法）
"""
    print("源码：")
    print(demo_source)
    run(demo_source)

    print("=" * 72)
    print("演示 2：括号改变优先级 + 左结合验证")
    print("=" * 72)
    demo_source = """\
a = 2 + 3 * 4;        # 乘法优先 -> 14
b = (2 + 3) * 4;      # 括号优先 -> 20
c = 100 - 20 - 5;     # 左结合 -> 75，若右结合会得 85
print a;
print b;
print c;
"""
    print("源码：")
    print(demo_source)
    run(demo_source)

    print("=" * 72)
    print("演示 3：布尔、float、最后一条语句可省略分号")
    print("=" * 72)
    run('flag = true;\nprint flag;\nprint flag + 1;\nprint 1.5 * 4')

    print("=" * 72)
    print("演示 4：错误报告（词法 / 语法 / 运行期三类）")
    print("=" * 72)
    # 下面这些用例里，前六个是真错误（应捕获到 CalcError），后两个演示
    # "看起来像错误、其实是合法语法"的情况——它们会正常执行并打印。
    bad_sources = [
        ("词法错误：非法字符", "x = 1 $ 2;"),
        ("词法错误：孤立小数点", "x = 1.;"),
        ("语法错误：少了分号", "x = 1\ny = 2;"),
        ("语法错误：括号没闭合", "print (1 + 2;"),
        ("语法错误：表达式没写完", "print 1 + ;"),
        ("语法错误：赋值漏了 =", "x 1;"),
        # `print(1);` 不是函数调用，而是"print 后面跟一个括号表达式"，因此是合法语法。
        # 保留这个用例，是为了让"本语言没有函数调用"这件事在演示里显式可见。
        ("注意：print(1) 是合法语法，会输出 1", "print(1);"),
        ("运行期错误：除以零", "x = 1;\ny = x / (x - 1);"),
        ("运行期错误：未定义变量", "x = 1;\nprint y + 1;"),
    ]
    for label, bad_source in bad_sources:
        print(f"\n[{label}]  源码：{bad_source!r}")
        try:
            run(bad_source)
        except CalcError as exc:
            print(exc.format())
        print()

    print("=" * 72)
    print("演示 5：注入 output，把结果当数据取回（便于测试）")
    print("=" * 72)
    captured: list[str] = []
    result = run("n = 6;\nprint n * 7;", output=captured.append)
    print(f"捕获到的输出行：{captured}")
    print(f"最后一条语句的值：{result!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
