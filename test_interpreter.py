"""interpreter.py 的回归测试：python -m unittest -v（或直接 python test_interpreter.py）。

{意图：断言的是**行为**（值、输出、错误类型、错误位置），不断言内部数据结构。因为
 Lexer/Parser/Interpreter 的分层还会调整，把测试绑在 Token 列表形状上会让重构寸步难行。}
取舍：没有引入第三方测试库，用标准库 unittest；本文件也不依赖任何外部依赖。
"""

import unittest

from interpreter import (
    CalcError,
    CalcRuntimeError,
    Interpreter,
    LexError,
    Lexer,
    ParseError,
    Parser,
    run,
)


def run_capture(source: str) -> tuple[list[str], object]:
    """执行源码，返回 (捕获到的输出行, 最后一条语句的值)。"""
    captured: list[str] = []
    result = run(source, output=captured.append)
    return captured, result


class LexerTest(unittest.TestCase):
    def test_token_stream(self):
        tokens = Lexer("x = 1 + 2.5;").tokenize()
        self.assertEqual(
            [t.type for t in tokens],
            ["IDENT", "ASSIGN", "NUMBER", "PLUS", "NUMBER", "SEMICOLON", "EOF"],
        )
        self.assertEqual(tokens[2].value, 1)
        self.assertEqual(tokens[4].value, 2.5)

    def test_position_is_one_based(self):
        tokens = Lexer("x = 1;").tokenize()
        self.assertEqual((tokens[0].line, tokens[0].column), (1, 1))
        self.assertEqual((tokens[2].line, tokens[2].column), (1, 5))

    def test_comment_is_skipped(self):
        tokens = Lexer("x = 1; # 注释里可以有 $ 和 print\n").tokenize()
        self.assertEqual([t.type for t in tokens], ["IDENT", "ASSIGN", "NUMBER", "SEMICOLON", "EOF"])

    def test_keywords(self):
        tokens = Lexer("print true false").tokenize()
        self.assertEqual([t.type for t in tokens], ["PRINT", "TRUE", "FALSE", "EOF"])

    def test_illegal_character_reports_position(self):
        with self.assertRaises(LexError) as ctx:
            Lexer("x = 1 $ 2;").tokenize()
        self.assertEqual((ctx.exception.line, ctx.exception.column), (1, 7))

    def test_trailing_dot_is_rejected(self):
        with self.assertRaises(LexError):
            Lexer("x = 1.;").tokenize()


class ParserTest(unittest.TestCase):
    def _parse(self, source: str):
        lexer = Lexer(source)
        return Parser(lexer.tokenize(), lexer.source_lines).parse()

    def test_precedence_multiplication_binds_tighter(self):
        # 2 + 3 * 4 的根节点必须是 '+'，右子节点才是 '*'。
        statement = self._parse("x = 2 + 3 * 4;")[0]
        self.assertEqual(statement.value.op, "+")
        self.assertEqual(statement.value.right.op, "*")

    def test_parentheses_override_precedence(self):
        statement = self._parse("x = (2 + 3) * 4;")[0]
        self.assertEqual(statement.value.op, "*")
        self.assertEqual(statement.value.left.op, "+")

    def test_missing_semicolon_reports_position(self):
        with self.assertRaises(ParseError) as ctx:
            self._parse("x = 1\ny = 2;")
        self.assertEqual(ctx.exception.line, 2)
        self.assertEqual(ctx.exception.column, 1)

    def test_unclosed_parenthesis_points_at_open_paren(self):
        with self.assertRaises(ParseError) as ctx:
            self._parse("print (1 + 2;")
        self.assertEqual((ctx.exception.line, ctx.exception.column), (1, 7))

    def test_incomplete_expression(self):
        with self.assertRaises(ParseError):
            self._parse("print 1 + ;")

    def test_last_statement_may_omit_semicolon(self):
        self.assertEqual(len(self._parse("x = 1")), 1)


class InterpreterTest(unittest.TestCase):
    def test_arithmetic_and_print(self):
        captured, _ = run_capture("x = 10; y = 3; print x + y; print x - y; print x * y;")
        self.assertEqual(captured, ["13", "7", "30"])

    def test_float_division(self):
        captured, _ = run_capture("print 10 / 4;")
        self.assertEqual(captured, ["2.5"])

    def test_integral_float_is_printed_without_decimal(self):
        # 6 / 3 显示为 2：本语言只有一种数值类型，用户不期待看到 2.0。
        captured, _ = run_capture("print 6 / 3;")
        self.assertEqual(captured, ["2"])

    def test_left_associativity(self):
        _, result = run_capture("100 - 20 - 5;")
        self.assertEqual(result, 75)

    def test_booleans_are_numbers_in_arithmetic(self):
        captured, _ = run_capture("flag = true; print flag; print flag + 1;")
        self.assertEqual(captured, ["true", "2"])

    def test_variable_reassignment(self):
        _, result = run_capture("x = 1; x = x + 41; x;")
        self.assertEqual(result, 42)

    def test_run_returns_last_statement_value(self):
        self.assertEqual(run("1 + 1;"), 2)

    def test_division_by_zero_has_position(self):
        with self.assertRaises(CalcRuntimeError) as ctx:
            run("x = 1;\ny = x / (x - 1);")
        self.assertEqual((ctx.exception.line, ctx.exception.column), (2, 7))
        self.assertIn("除以零", ctx.exception.message)

    def test_undefined_variable_lists_known_names(self):
        with self.assertRaises(CalcRuntimeError) as ctx:
            run("a = 1;\nprint b;")
        self.assertIn("'b'", ctx.exception.message)
        self.assertIn("a", ctx.exception.message)

    def test_interpreter_state_survives_across_run(self):
        # 同一 Interpreter 可以被多次 run：验证语法树是数据、解释器是可复用的执行器。
        lexer = Lexer("x = 1;")
        interpreter = Interpreter(lexer.source_lines, output=[].append)
        interpreter.run(Parser(lexer.tokenize(), lexer.source_lines).parse())
        lexer2 = Lexer("x = x + 1;")
        interpreter.source_lines = lexer2.source_lines
        interpreter.run(Parser(lexer2.tokenize(), lexer2.source_lines).parse())
        self.assertEqual(interpreter.variables["x"], 2)


class ErrorHierarchyTest(unittest.TestCase):
    def test_all_errors_share_a_base_class(self):
        for source, error in [
            ("x = 1 $ 2;", LexError),
            ("x = 1\ny = 2;", ParseError),
            ("print z;", CalcRuntimeError),
        ]:
            with self.assertRaises(CalcError) as ctx:
                run(source)
            self.assertIsInstance(ctx.exception, error)

    def test_format_contains_line_column_and_caret(self):
        try:
            run("x = 1 $ 2;")
        except CalcError as exc:
            report = exc.format()
        self.assertIn("第 1 行", report)
        self.assertIn("^", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
