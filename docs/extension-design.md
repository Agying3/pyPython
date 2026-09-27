# 从 calc 走向真语言：扩展设计说明

本文针对 `interpreter.py`（下称 **calc**）的扩展，目标状态是一个能支撑真实程序的语言。

**本文只讲设计与取舍，不含实现代码。** 但每个结论都标了它依据的是哪一段现有代码，
以及**哪一行会被推翻**——因为这份文档最大的价值不是"要加什么功能"（那个列个清单就够了），
而是**加的先后顺序**。顺序错了会白写两遍。

---

## 0. 先说结论：你选的四项 + 一项，是一次重写，不是四次扩展

你勾选的是：控制流、函数、数据类型、错误恢复，外加本文。这五项看起来是平行的，其实不是：

```
控制流 + 错误恢复 ──► 不需要动数据模型，可以在现有架构上直接长出来
函数              ──► 推翻 Environment（全局 dict 必须变成作用域链）
数据类型          ──► 推翻值模型（现在"值就是 Python 的 int/float/bool"）
```

**关键结论：第 2 项（函数）会让第 1 项（控制流）里写好的部分代码需要回头改。**
具体地说，`while` 循环体如果直接复用 `Interpreter._execute`，那么等作用域链引入后，
`_execute` 的签名必须从 `(node)` 变成 `(node, env)`，所有循环语句的执行路径都要跟着改。

所以推荐顺序是 **类型 → 作用域 → 函数 → 控制流 → 错误恢复**，理由见第 4 节。
这个顺序和你勾选的清单顺序不同，是刻意的：先定值模型和作用域，再往上堆语法。

---

## 1. 现有代码的哪些部分会存活

先划清楚，避免推翻得过多。按"扩展时是否会改"分三类：

| 层 | 现状位置 | 扩展时 |
|---|---|---|
| `Lexer` 主循环 | `interpreter.py:170-230` 左右 | **基本存活**。只需加关键字和 token 类型 |
| `Token` 数据结构 | `interpreter.py:129-145` | **存活**。字段够用 |
| `CalcError` 基类 + `format()` | `interpreter.py:93-119` | **存活**。带位置报错的设计是这项工程里最值钱的部分，直接继承 |
| `Parser` 的 token 游标 | `interpreter.py:397-439` | **存活**。`_peek/_advance/_expect` 机制不变 |
| `Parser._error` 的"指向上一个 token" | `interpreter.py:414-421` | **存活**，但错误恢复要加新东西，见第 6 节 |
| `SINGLE_CHAR_TOKENS` 单字符映射 | `interpreter.py:81-90` | **必须推翻**，见 2.1 |
| `Interpreter.variables`（全局 dict） | `interpreter.py:621` | **必须推翻**，见第 3 节 |
| `Interpreter.BINARY_OPS` | `interpreter.py:613-618` | **必须推翻**。它假设"两个数字进去、一个数字出来" |
| `Interpreter._execute(node)` 签名 | `interpreter.py:640` | **必须改签名**（加 env 参数） |
| `_format_value` 里 float 去小数点 | `interpreter.py:721-734` | **要重新讨论**，见 2.4 |

值得说的是：**Lexer 和 Parser 的骨架几乎不用动，被推翻的全在 Interpreter。**
这不是巧合——它说明当初把三层分开是对的，代价集中在最上层。

---

## 2. 第一步：值模型与类型系统

### 2.1 为什么必须先做这个

现在 `_evaluate` 的隐含契约是"表达式求值的结果是 Python 的 int/float/bool"
（`interpreter.py:661-688` 的 docstring 明写"返回值本身（int/float/bool）"）。
`BINARY_OPS` 用 `lambda a, b: a + b` 直接调 Python 的 `+`（`interpreter.py:613-618`）。

**这个设计在只有数字时是对的，加了字符串/列表之后立刻产生 bug**：

```python
# 本语言的 '+' 应该是什么语义？
"a" + "b"    # 拼接，对
1 + "a"      # 必须报错，不能变成 Python 的 TypeError 泄漏出去
[1,2] + [3]  # 拼接？还是逐元素相加？
```

如果继续用 `lambda a, b: a + b`，`1 + "a"` 会抛 Python 的 `TypeError`，
**而那个异常没有行号**——`_eval_binop` 里的 `except TypeError` 虽然拦住了
（`interpreter.py:702-710`），但错误信息会变成"运算符 '+' 不支持 int 与 str 的运算"，
暴露了 `int`/`str` 这种**实现层类型名**。用户不该看到 Python 的类型名。

**结论：需要一个显式的、独立于 Python 的值类型系统。**

### 2.2 设计选项

**方案 A：继续用 Python 原生类型，靠 `isinstance` 分派**
- 优点：零成本，`_format_value` 那套还能用。
- 缺点：类型名会泄漏；`bool` 是 `int` 的子类，`isinstance(True, int)` 为真，
  排序/比较会出微妙 bug；无法表达"本语言的整数溢出"这类自定义语义。
- **不推荐。**

**方案 B：自定义值对象（推荐）**

```python
class Value: ...                    # 抽象基类，所有语言值
class NumberValue(Value): ...       # 包一个 int 或 float
class StringValue(Value): ...
class ListValue(Value): ...
class BoolValue(Value): ...
class FunctionValue(Value): ...     # 见第 3 节
class NilValue(Value): ...
```

- 优点：类型名完全可控；运算符语义集中在一处分派；将来加类型检查有地方挂。
- 缺点：**每个值都要包一层**，性能下降（对本项目的目标可接受），
  且 `_format_value` 必须重写成 `Value.__str__`。
- **推荐。** 理由：你说目标是"长成一个真语言"，真语言的类型语义迟早要自己控制。

**方案 C：混合——数字用 Python 原生，只给新类型建对象**
- 优点：现有代码改动最小。
- 缺点：**两套类型模型并存是最坏的选项**，分派逻辑会到处写 `isinstance(x, Value)` 判断。
- **不推荐。**

### 2.3 运算符分派怎么做

现在是 `BINARY_OPS` 字典 + lambda。改成方案 B 后，建议**按"左操作数类型"分派**：

```
NumberValue.__add__(other):
    if other is NumberValue: 返回 NumberValue
    否则: raise TypeError("数字不能与 <other类型名> 相加")
```

这不是 Python 的 `__add__` 协议，而是**本语言自己的方法**，由 `_eval_binop` 显式调用。
区别很重要：不要直接让 `Value` 去实现 Python 的运算符重载，否则
`a + b` 在解释器代码里会静默变成语言语义，读代码的人分不清哪行是"宿主运算"、
哪行是"被解释的运算"。**建议方法名用 `add`、`sub` 而不是 `__add__`。**

### 2.4 顺带要重新决定的：`6 / 3` 显示成 `2`

`_format_value`（`interpreter.py:721-734`）现在把整数值的 float 显示成整数。
这个决定**在只有数字时勉强成立，有字符串后就危险了**：一旦有 `str()` 内置函数，
`str(6/3)` 得到 `"2"` 还是 `"2.0"`？如果显示和转换不一致，就会出现
`print x` 显示 `2` 但 `x == 2.0` 比较为真的混乱。

**建议在方案 B 里一并解决**：区分 `NumberValue` 的内部表示（int/float 标记）
和显示规则，并且让 `str()` 转换走**同一个**格式化函数，保证一致。

---

## 3. 第二步：环境与作用域（推翻全局 dict）

### 3.1 被推翻的那一行

```python
# interpreter.py:621
self.variables: dict[str, Any] = {}
```

以及所有 `self.variables[...]` 的读写（`interpreter.py:648, 671-679`）。
`_known_names()`（`interpreter.py:712-714`）在作用域链下也没法"列出全部变量"了。

### 3.2 设计

```python
class Environment:
    def __init__(self, parent=None):
        self.values = {}
        self.parent = parent

    def define(self, name, value): ...   # 只在当前层定义
    def lookup(self, name):              # 沿链向上找
    def assign(self, name, value):       # 找到已有的那层并更新；找不到则报错
```

**关键决策：`define` 和 `assign` 必须是两个方法。**
现在 calc 里"首次赋值即声明"（`Assign` 直接 `self.variables[name] = value`）。
有了作用域后，"赋值"到底是在当前层新建，还是修改外层已有的，**是语言设计问题**：
- 若 `assign` 找不到就新建 → 类似 Python 的简单模型，但闭包修改外层变量会很别扭
- 若 `assign` 找不到就报错 → 必须显式声明（`var x = 1`），能早发现拼写错误
- **推荐**：先按"找不到就报错"，逼自己引入 `var` 关键字。理由：拼错变量名导致
  静默创建新变量，是脚本语言里最难查的一类 bug，而报错几乎不花成本。

### 3.3 `Interpreter` 的签名变化

```python
# 现在
def _execute(self, node): ...
def _evaluate(self, node): ...

# 之后
def _execute(self, node, env): ...
def _evaluate(self, node, env): ...
```

**这就是为什么函数必须排在控制流之前**：如果先写 `while`，循环体的执行调用
`_execute(node)`；等加了 env，所有这类调用点都要改。先定 env，控制流一次写对。

注意 `Interpreter.__init__` 里的 `source_lines`（`interpreter.py:622`）可以留着不动，
它和变量存储无关。**但 `self.variables` 要移交给 Environment。**

---

## 4. 第三步：函数与调用栈

### 4.1 函数值怎么表示

函数定义 `fn add(a, b) { return a + b; }` 求值后，应该产生一个 `FunctionValue`，
它捕获**定义时的环境**（闭包）：

```python
class FunctionValue(Value):
    params: list[str]
    body: list[Node]
    closure: Environment      # 关键：不是调用时的环境
```

**如果这里存的是调用时的环境，闭包就是坏的。** 这是解释器实现里最经典的坑，
也是为什么第 3 节必须先做。

### 4.2 返回怎么实现

设计选项：

**方案 A：用 Python 异常做返回**（`ReturnSignal(Exception)` 携带返回值）
- 优点：不管嵌套多深，一行 `raise` 就能跳出；实现最简单。
- 缺点：异常做控制流，性能差；且容易和真正的错误混淆（要小心别被
  `except CalcError` 误捕获——`ReturnSignal` **不能**继承 `CalcError`）。

**方案 B：返回值约定**（`_execute` 返回 `(value, did_return)` 之类的哨兵）
- 优点：没有异常开销，语义清晰。
- 缺点：**每个 `_execute` 调用点都要检查哨兵**，漏一个就静默不返回。

**方案 C：显式控制流对象**（返回 `FlowSignal`，区分 `Normal`/`Return`/`Break`/`Continue`）
- 优点：**一套机制同时解决 `return`、`break`、`continue`**，且都不是异常。
- 缺点：最啰嗦，每个语句执行器都要处理。

**推荐 C。** 理由：你第 1 项就要了控制流，`break`/`continue` 迟早需要同类机制；
用异常做 return（方案 A）之后，加 `break` 时要么再造两个异常类型，要么返工。
一次做对比两次做错便宜。**注意 C 会让"忽略返回值"变成一个真实的危险**
（`_execute(node, env)` 忘了接哨兵 → 循环里的 return 被吞掉），这是它的主要代价。

### 4.3 递归与调用深度

`fn f() { return f(); }` 会直接把 Python 栈打爆，抛 `RecursionError`——
**这个异常没有行号**。必须在 `_call` 里自己维护调用深度计数器，
超限时报"调用太深"，并带上**调用点**的位置（这一步做起来比听起来麻烦：
需要维护一个调用点位置栈，因为错误发生在被调函数内部，但用户想知道是谁调的）。

---

## 5. 第四步：控制流与比较/逻辑运算

### 5.1 短路求值是正确性问题，不是优化

`and` / `or` **必须**短路：

```
false and f();    # f() 绝对不能被执行
true or f();      # 同上
```

这意味着它们**不能**走 `_eval_binop` —— 现在的 `_evaluate` 在
`interpreter.py:681-684` 是**先把 left 和 right 都求值再运算**。所以
`and`/`or` 需要在 `_evaluate` 里单独分发，**先求左边，再决定要不要碰右边**。
建议把它们建成独立的 AST 节点（`Logical`），而不是复用 `BinOp`，
这样类型上就杜绝了"误用 eager 求值"的可能。

### 5.2 比较运算

`== != < <= > >=`。要注意：
- 现在是 `=` 一个 token（`interpreter.py:88`），加 `==` 后
  **`SINGLE_CHAR_TOKENS` 那张单字符表就不够用了**（`interpreter.py:81-90` 的注释里
  已经预言了这一点："一旦加入 ==，就必须改成最长匹配"）。Lexer 要改成：
  先看两个字符，再退回一个字符。
- `<=` `>=` `!=` 同理，都是双字符。

这个是**纯 Lexer 改动，不碰其他层**——再次说明当初的分层是对的。

### 5.3 优先级表

加了比较和逻辑后，层级变多，建议明确列表（由低到高）：

```
or  →  and  →  相等(== !=)  →  比较(< <= > >=)  →  加法(+ -)  →  乘法(* /)  →  一元(- !)  →  调用/索引  →  原子
```

**递归下降的写法是"每个优先级一个函数"**，所以这张表就是一串函数调用关系。
现在 calc 的 `_expression/_term/_factor`（`interpreter.py:526-586`）会扩展成 8 个左右的函数。
注意 `_factor` 现在同时管"原子"和"括号"（`interpreter.py:564-577`），
加了函数调用和索引后，建议把"后缀运算"（`f(x)`、`a[i]`）单独拆一层，
因为它们**可以链式出现**（`f(x)[0](y)`）。

---

## 6. 第五步：错误恢复

### 6.1 现状

`Parser._error`（`interpreter.py:414-421`）抛异常→一路冒泡→程序结束。一错全停。

### 6.2 设计

要"一次报告多个错误"，Parser 主循环要改成：

```
parse():
    statements = []
    errors = []
    while not at_end():
        try:
            statements.append(statement())
        except ParseError as e:
            errors.append(e)
            synchronize()        # 丢弃 token 直到语句边界
    return statements, errors    # 注意：返回值变了
```

**`synchronize()` 是这里唯一有技术含量的部分**：出错后要丢 token 直到
一个**可信的重新开始点**。常见策略（按可靠性排序）：
1. 丢到下一个 `;`（最可靠，因为分号是唯一语句边界）
2. 丢到下一个语句起始关键字（`if`/`while`/`fn`/`print`）
3. 丢到 `}`

建议只用 1 和 2。**不要用"丢到换行"**：calc 里换行不是语句边界
（`interpreter.py:51` 明写"分行不是语句边界"），用了会导致恢复点错误，
进而报出一堆假错误——**假错误比少报错误更糟**，因为它会让用户去改本来正确的代码。

**注意 `Parser.parse()` 的返回值从 `list[Node]` 变成 `(list[Node], list[ParseError])`，
这是破坏性改动，`run()`（`interpreter.py:743` 附近）和所有测试都会受影响。**

### 6.3 运行期错误恢复

运行期错误（未定义变量等）**不建议**恢复继续执行。理由：语法错误可以靠
`;` 确定边界，运行期错误发生时程序状态已经不可信，继续跑可能产生
大量级联错误。**建议：运行期首个错误即停，只有 Parser 层做多错误恢复。**

---

## 7. 还应该顺手考虑的（现在不做，但别堵死）

这些不在你勾选的四项里，但会影响上面的决策，所以现在就要避免"堵死"：

- **`print` 是语句还是函数？** 现在 `PRINT` 是关键字（`interpreter.py:73`），
  意味着 `print` 不能当变量名、不能被传递。如果将来想要一等公民的函数，
  `print` 应该降级成内置函数 `FunctionValue`。**建议现在别急，但别在
  `_statement`（`interpreter.py:450-477`）里把 `print` 特殊化得更深。**
- **`;` 是必需的。** 有 `if`/`while` 的块结构后，通常改成用 `{}` 分块，
  `;` 变成可选。这会**再次推翻** `_expect_statement_end`（`interpreter.py:512-524`）。
- **注释 `#`**：带了字符串之后，`#` 在字符串里不该是注释。现在 Lexer
  无条件把 `#` 当注释（`interpreter.py:180` 附近），加字符串时必须改成
  "在字符串内部不认注释"。**这是个典型的"加了字符串就悄悄坏掉"的地方。**
- **`Interpreter` 每次 `run` 复用状态**：测试 `test_interpreter_state_survives_across_run`
  依赖了这个行为。引入 Environment 后要决定：Environment 是每次 run 新建，
  还是持久（REPL 需要持久）。**这个决定会影响 `run()` 的签名。**

---

## 8. 建议的落地顺序（每步都可运行、可测试）

| 步骤 | 内容 | 推翻什么 | 是否可独立交付 |
|---|---|---|---|
| 1 | 值模型（方案 B）+ 字符串类型 | `BINARY_OPS`、`_format_value` | 是 |
| 2 | Environment 作用域链 + `var` 声明 | `self.variables`、`_execute/_evaluate` 签名 | 是 |
| 3 | 比较/逻辑运算符 + 短路 + 最长匹配 Lexer | `SINGLE_CHAR_TOKENS` | 是 |
| 4 | `if` / `while` + `FlowSignal` 控制流 | 无（新增） | 是 |
| 5 | 函数/闭包/return/调用深度 | 复用步骤 4 的 FlowSignal | 是 |
| 6 | 列表 + 索引 + 内置函数 | 依赖步骤 1 | 是 |
| 7 | Parser 错误恢复 | `parse()` 返回值 | 是 |

**每一步都应该在 `test_interpreter.py` 里补测试再进下一步。**
现有 24 个测试是这套重构唯一的安全网——它们断言的是行为而不是内部结构
（`test_interpreter.py` 开头注释里说的），所以应该能在重构中大部分存活；
**如果某一步让大量现有测试失败，说明那一步的抽象选错了，应该回头改设计而不是改测试。**

需要特别标记的：`test_interpreter_state_survives_across_run` 在步骤 2 一定会
需要修改（它直接断言 `interpreter.variables["x"]`），这是预期内的。

---

## 9. 本文未验证的部分（明确声明）

- 第 4.2 节推荐方案 C（FlowSignal）是基于"你第 1 项就要控制流"的**推断**，
  没有实际写过对照实现。如果你只想要 `return` 不想要 `break`/`continue`，
  方案 A（异常）更省事，这个取舍我无法替你定。
- 第 6.2 节的 `synchronize()` 策略没有经过真实错误样本检验。
  假错误率到底如何，要写完拿真实错代码试才知道。
- 性能影响完全没测。方案 B（值对象包装）会让每次算术多一层对象分配，
  量级估计是"明显变慢"，但**不打算在本文里给具体数字**，因为没测。
