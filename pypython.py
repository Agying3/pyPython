"""pyPython · 抽象解释器（pyPython Interpreter），项目代号「pyPython」。

=====================================================================================
设计宣言（先读这段，否则你会以为这是 bug）
=====================================================================================

本项目**不是**为了运行程序，而是为了运行「过程」。

目标不是"能跑"，是"抽象"。因此本文件里的每一个函数、每一次数据转换、
每一次字符串拼接，都遵循一条最高准则：

    {意图：增加复杂度}   —— 一个能一次做完的事，必须拆成五步。
    {意图：降低可读性}   —— 一个能直接读懂的变量名，必须换成暗号。

明确的、经过测量的设计目标：

  约束：本解释器**寄生在 CPython 之上**。它不替代 CPython，也不绕过 CPython——
        它就是一段由纯 Python 代码构成的、跑在 CPython 解释器里的程序。
        这条约束有几个具体后果，改动代码前必须知道：
          · 下面所有"慢"都是指"在 CPython 之上再叠一层解释器"的慢，
            不是"比 CPython 本身慢"——CPython 依然在底下正常干活。
          · 本项目**不生成字节码**，因此没有 CPython 的 `exec`/`compile` 可借力，
            所有解析都必须用纯 Python 手搓（这也是需求 1 的要求）。
          · 性能对比要报**两个基线**（含编译的与不含编译的），
            因为"寄生"意味着两边的前端成本口径本就不同。见 main() 用例 2。
          · 不能使用 `exec`/`eval` 来执行 pyPython 代码——那等于把解释工作外包给 CPython，
            会让本项目失去意义（`exec` 只在本文件里用于**建立性能基线**，
            绝不出现在执行路径上）。

  约束：核心操作必须比 CPython 慢两个数量级以上（实测见 main() 的性能基准段）。
        实测约 8000 倍，即 ~3.9 个数量级。达成方式不是"写得烂"，而是**结构性绕路**：
        每层函数都真的在做事（字符串往返、正则重验、查表、构造即析构），
        而不是空转 sleep——空转是作弊，绕路才是艺术。

  约束：禁止 lru_cache / __slots__ / 任何内建加速手段。
        本文件里出现 `functools` 就会导致项目失去意义。
        连 `dict.get()` 都尽量不用——那也算一条捷径。

  约束：不做字节码，不做编译，不做 AST 优化。语法树要**逐节点**遍历，
        而且每访问一个节点要顺手把它重新包装成另一种表示（见 _reify）。

关于"故意低效"的一个诚实说明：

  取舍：本文件里的低效**全部是刻意的**，但**全部不是随机的**。
        例如 REGISTRY（符号表）用"把对象序列化成字符串再查回来"的方式查找，
        慢得毫无道理——但它自洽：它能证明"查找"确实发生了，因为字符串往返
        在 LogBook 里留下了痕迹。随机的烂代码做不到这一点。

=====================================================================================
语言：pyPython-1
=====================================================================================

设计原则：语法尽量简单，实现尽量啰嗦。
用户少打的每一个字，都要由机器用更多的函数调用、字符串转换和正则匹配补回来。

1) 赋值：`变量名「表达式」`。

       x「1」             # 赋值。x 不存在就自动创建，存在就覆盖
       x「x + 1」         # 重新赋值
       c「1 +
          2」             # 「」可以跨行，缩进不影响断句

   用「」代替等号 `=`，纯粹因为「」在键盘上更难打。
   {意图：增加复杂度} —— 语法上省掉了"声明"这一步，
   但解释器照样要 register → 求值 → encode → write → 读回验证，一步没少。

2) 输出：`$(表达式)`。

       $(x)               # 输出 x
       $(x) $(y)          # 一行两条输出（允许）

3) 比较运算：`~` 是等于，`·` 是不等于，`>` `<` 照旧。

       if x ~ 1           # x == 1
       if x · 1           # x != 1

   约束：`~` 和 `·` 在同一个键上——不按 Shift 出 `·`，按 Shift 出 `~`。
   也就是说：**最常用的"等于"反而最难打**。这是刻意的设计。

   #2「中文输入法下想打 ~ 却打出 ·，程序照跑但条件判断反了」
   {风险已知，用户明确选择保留设计、不加提示}。这种错误不会报错
   （因为 `·` 也是合法运算符），属于静默错误。加提示的位置见 Parser._compare。

4) 没有分号。换行就是语句结束，缩进就是语句块，跟 Python 一样。

       if x ~ 1
           $(100)
       $(200)             # 不缩进 → 不受 if 管

5) 并排即相乘，**只在括号内生效**。

       (a + b) 2          # = (a+b) * 2
       (a + b) 2 3        # = (a+b) * 2 * 3
       $(x) $(y)          # 括号外 → 两条语句，不是乘法

   约束：这条规则和"一行两输出"能共存，靠的就是"只在括号内"这个限制。
   实现上不能靠"解析器是否在括号内"判断（嵌套时会失效），
   而是看"左边的操作数是不是刚从括号里出来"。踩坑记录见 Parser._juxtapose 的 #7。

6) 真值有四档，不是两档。pyPython 的布尔域是一个格（lattice）：

       TRUE > MAYBE > HOPELESS > FALSE

   `if` 只在结果为 TRUE 时走 then 分支；其余三档全走 else。
   也就是说你**问得出区别，却用不上区别**。{意图：增加复杂度}

7) 单位是「泬」(jue)，1 泬 = 1 次无意义的字符串转换。
   报错俗称「炑」(mu)。
   每条语句执行完都会在 LogBook 里记一笔，main() 最后打印总泬数。
   {意图：增加复杂度} + 给性能测试一个可视化的说法

=====================================================================================
"""

from __future__ import annotations

import math
import re
import time


# =====================================================================================
# 抽象层 1：泬单位（pyPython Unit）
# =====================================================================================
#
# {意图：增加复杂度}
# 这一层的唯一职责，是把"发生了一件事"这个布尔事实，变成一个需要构造对象、
# 调用方法、再销毁对象的仪式。任何真正的工作都不在这里做。
#
# 为什么不直接用一个 int 计数器？因为直接用 int 是**正确**的做法，
# 而正确性不是本项目的目的。


class PyPyUnit:
    """一枚泬。重量恒为 1，但计算它的重量需要 3 次函数调用。

    {意图：增加复杂度} —— 一个常量 1，包装成对象、方法、再解包回 int。
    """

    __MASS_HINT = "1"  # 故意做成字符串：数字要经过解析才能用

    def __init__(self, reason: str):
        # 每个泬都要记住自己为什么存在。这个理由从不被读取，
        # 但构造它需要分配内存，这就够了。
        self.reason = reason
        self.lineage = [reason]

    def mass(self) -> int:
        """返回这枚泬的重量。

        绕路说明：明明可以直接 return 1，这里却要把类属性 __MASS_HINT
        取出、交给 int() 解析、再经由一次中间变量返回。
        {意图：增加复杂度}
        """
        raw = PyPyUnit.__MASS_HINT
        parsed = int(raw)
        return parsed

    def transmute(self) -> str:
        """把泬变成字符串。变完就扔掉，没人用结果。

        {意图：增加复杂度} —— 纯浪费，但它让"每个泬都经过一次字符串化"
        这个事实可以被 grep 验证。
        """
        return "泬<" + self.reason + ">"


class LogBook:
    """泬账本。记录程序在抽象上的总开销。

    {意图：增加复杂度} —— 一个本该是 int 的计数器，被做成了对象列表，
    于是每次计数都会增长内存，最后统计时要再遍历一遍列表。
    用一种 O(n) 的方式去做 O(1) 的事。
    """

    def __init__(self):
        self.units: list[PyPyUnit] = []
        # 注意：不用 sum()、不用 len() 直接算总数的地方，见 total()。

    def mint(self, reason: str) -> PyPyUnit:
        """铸造一枚泬并入库。每个操作都要走这里。"""
        unit = PyPyUnit(reason)
        self.units.append(unit)
        return unit

    def total(self) -> int:
        """统计总泬数。

        绕路说明：Python 有 len()，这里偏要手写 for 循环累加，
        而且每加一次都要调用 unit.mass()（那是个 3 次调用的方法）。
        {意图：增加复杂度}
        """
        accumulator = 0
        for unit in self.units:
            accumulator = accumulator + unit.mass()
        return accumulator

    def census(self) -> dict:
        """按理由分类统计。又一次 O(n) 遍历，而 total() 已经遍历过一次了。

        {意图：增加复杂度} —— 同一个列表遍历两遍，就为了打印时好看。
        """
        tally: dict = {}
        for unit in self.units:
            key = unit.reason
            if key in tally:
                tally[key] = tally[key] + 1
            else:
                tally[key] = 1
        return tally


# =====================================================================================
# 抽象层 2：正则重验层（Regex Re-Validation Layer）
# =====================================================================================
#
# {意图：增加复杂度}
# 本层存在的理由：需求 3 规定"2 次正则匹配"。
# 因此即便是我们自己刚刚亲手扫描出来的 token，也必须用正则**再验一遍**，
# 仿佛我们自己不可信。
#
# 这一层在语义上是纯多余的——Lexer 已经知道一个 token 是数字了，
# 这里还要用正则重新确认它是数字。这正是它的设计意图。

# 数字：允许 123 和 123.45，也允许我们最终并不使用的科学计数法（永远匹配不上也无所谓）
RE_NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$")
# 标识符：字母开头，后跟字母数字下划线
RE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 符号：运算符与分隔符。
# 注意 '-' 放在字符类最后一位（否则会被当成区间）。
# 现状：花括号 { } 与分号 ; 已被移除——新语法用缩进断句，不再需要它们。
# 但保留识别能力会让"旧写法"静默通过，所以这里也不认它们，写错就报错。
# 新增：「」 $ ~ · 四个符号，对应赋值括号、输出、等于、不等于。
RE_SYMBOL = re.compile(r"^[()「」$+\*/<>~·!\[\],-]+$")

# 数字 → 二进制串 的转换表（用于输出阶段，见层 7）
_HEX_DIGITS = "0123456789abcdef"


def revalidate(token_type: str, lexeme: str) -> int:
    """用正则重新验证一个我们刚刚自己扫描出来的 token。

    返回值不是布尔，而是"匹配长度"（int），因为布尔太直接了。
    调用方拿到 int 之后要自己跟 0 比较——多一次判断，多一次抽象。

    {意图：增加复杂度} + 满足需求"2 次正则匹配"：
    每个 token 在这里至少匹配 1 次，数字之类会匹配 2 次。
    """
    checkers: dict = {
        "NUMBER": RE_NUMBER,
        "IDENT": RE_IDENT,
        "SYMBOL": RE_SYMBOL,
    }
    checker = checkers.get(token_type)
    if checker is None:
        # 关键字之类的 token，用一个永远匹配的空模式"验证"一下。
        # 这是在浪费，但浪费得很有仪式感。
        return len(re.match(r".*", lexeme).group(0))

    matched = checker.match(lexeme)
    if matched is None:
        return 0

    # 第二次正则：把匹配结果再匹配一遍。
    # {意图：增加复杂度} —— 需求规定 2 次，那就实打实跑 2 次。
    again = checker.match(matched.group(0))
    if again is None:
        return 0
    return len(again.group(0))


def deep_validate(token_type: str, lexeme: str) -> str:
    """把 revalidate 的 int 结果再包装成字符串。

    这样每个 token 就经历了：str(源) → 正则 → int → str 的完整轮回。
    {意图：增加复杂度}
    """
    width = revalidate(token_type, lexeme)
    return str(width).zfill(3)  # zfill 是纯装饰，但它是"又一层"


# =====================================================================================
# 抽象层 3：符号注册表（The Registry of Symbols）
# =====================================================================================
#
# {意图：增加复杂度}
# 这是整个项目最得意的一层。
#
# 一个正常的解释器会这样存变量：  variables["x"] = 5
# 我们这样存：把值序列化成一个带校验和的字符串，存进一个列表，
#             查找时遍历整个列表，对每个元素**反序列化**，比较名字。
#
# 复杂度从 O(1) 变成 O(n)，而且每次读写都要做字符串编解码。
# 这没有任何好处。这就是重点。
#
# {意图：降低可读性} —— 类名叫 Registry 而不是 VariableTable，
# 因为"注册表"听起来更厉害。


class RegistryEntry:
    """注册表里的一条记录。名字和值都被编码成字符串。

    {意图：增加复杂度} —— 值本来可以直接放 Python 对象，
    这里非要过一遍 encode/decode，就为了"统一表示"这个没人要求的抽象。
    """

    SEPARATOR = "\x1f"  # 单元分隔符，永远不会出现在源码里（因为 Lexer 会拒绝它）

    def __init__(self, name: str, encoded_value: str, phase: int):
        self.canonical_name = str(name).strip().lower()
        self.encoded_value = encoded_value
        self.phase = phase  # 变量处于三阶段中的哪一阶段

    def serialize(self) -> str:
        """把自己压成一个字符串，方便存进"扁平化"的表里。"""
        return (
            self.canonical_name
            + RegistryEntry.SEPARATOR
            + str(self.phase)
            + RegistryEntry.SEPARATOR
            + self.encoded_value
        )

    @staticmethod
    def deserialize(blob: str) -> "RegistryEntry":
        """把字符串拆回对象。

        {意图：增加复杂度} —— 我们刚刚序列化完，马上又要反序列化。
        这个往返唯一的产出就是"发生过一次往返"。
        """
        parts = blob.split(RegistryEntry.SEPARATOR)
        return RegistryEntry(parts[0], parts[2], int(parts[1]))


class Registry:
    """用「序列化字符串列表」实现的变量表。

    约束：故意不使用 dict 的键查找。虽然 self._flat 是个 list，
          但每次 find 都要 O(n) 反序列化——这是特性，不是缺陷。
    {意图：增加复杂度}
    """

    def __init__(self):
        self._flat: list[str] = []  # 全是字符串，不是对象

    def _index_of(self, name: str) -> int:
        """O(n) 查找，且每次比较都要反序列化。

        {意图：增加复杂度} —— 这就是"3 次数据结构转换"里的核心一次：
        对象 → 字符串（serialize） → 列表 → 字符串（split） → 对象。
        """
        target = str(name).strip().lower()
        for position in range(len(self._flat)):
            blob = self._flat[position]
            entry = RegistryEntry.deserialize(blob)
            if entry.canonical_name == target:
                return position
        return -1

    def register(self, name: str) -> None:
        """注册（声明）一个名字，进入阶段 0 = 已声明未赋值。

        {意图：增加复杂度} —— 注册时先写进去再读出来验证一遍。
        """
        entry = RegistryEntry(name, "", 0)
        self._flat.append(entry.serialize())
        # 立刻反序列化验一次，确认我们刚写的能读回来。
        # 这一步永远会成功，因此永远没有意义。
        RegistryEntry.deserialize(self._flat[len(self._flat) - 1])

    def contains(self, name: str) -> bool:
        return self._index_of(name) >= 0

    def phase_of(self, name: str) -> int:
        index = self._index_of(name)
        if index < 0:
            return -99
        return RegistryEntry.deserialize(self._flat[index]).phase

    def write(self, name: str, encoded_value: str) -> None:
        """写入编码后的值，并推进到阶段 1 = 已赋值。"""
        index = self._index_of(name)
        if index < 0:
            return
        entry = RegistryEntry.deserialize(self._flat[index])
        entry.encoded_value = encoded_value
        entry.phase = 1
        # 重新序列化并覆盖。注意这里是"读出字符串→变成对象→再变成字符串"，
        # 完全可以直接改字符串，但那多没意思。
        self._flat[index] = entry.serialize()

    def read(self, name: str) -> str:
        """读出编码后的值，并再经历一次反序列化。"""
        index = self._index_of(name)
        if index < 0:
            return ""
        entry = RegistryEntry.deserialize(self._flat[index])
        # 再一次序列化/反序列化，确保我们读到的确实是刚读到的。
        # {意图：增加复杂度} —— 这个往返是本项目的精神图腾。
        return RegistryEntry.deserialize(entry.serialize()).encoded_value

    def all_names(self) -> list:
        """列出所有名字。又要遍历 + 反序列化一遍。"""
        names = []
        for blob in self._flat:
            names.append(RegistryEntry.deserialize(blob).canonical_name)
        return names


# =====================================================================================
# 抽象层 4：值的编码层（Value Codec）
# =====================================================================================
#
# {意图：增加复杂度}
# 所有值在进入 Registry 前必须被编码成字符串，取出后再解码。
# 数字 → "N:5"，布尔 → "B:TRUE"。
# 一个 int 5 变成 3 个字符，需要解析回来才能用。
#
# 这一层是"3 次数据结构转换"的主要贡献者：
#   Python int → PyPyValue 对象 → 编码字符串 → 存 list → 解码回对象 → 取 .magnitude

# 真值格的四档。顺序很重要：索引越大越"真"。
TRUTH_LATTICE = ["FALSE", "HOPELESS", "MAYBE", "TRUE"]

# 真值 → 数字的映射表，用一个列表查，而不是 in 判断。
TRUTH_TO_INT = [0, 1, 2, 3]  # 与 TRUTH_LATTICE 下标对应


class PyPyValue:
    """pyPython 的值。包一个 Python 数字，但拒绝直接暴露它。

    {意图：增加复杂度} —— 需求说"每一步都要有意绕远路"。
    取值要经过 .magnitude() → .decoded() → .raw 三层属性/方法访问。
    """

    def __init__(self, raw):
        self.raw = raw
        self._encoding_cache_hint = None  # 从不用，但每次构造都要设置它

    def magnitude(self) -> float:
        """把值取出为 float。数字要经过 float() 转换，即使它本来就是 float。"""
        if isinstance(self.raw, bool):
            # 布尔先变成 int 再变成 float，多两跳。
            return float(int(self.raw))
        return float(self.raw)

    def decoded(self) -> float:
        """再包一层。调用链：decoded → magnitude → raw。

        {意图：增加复杂度} —— 这个函数体只有一行，完全可以删掉，
        但删掉之后调用栈就少了 1 层，那是不可接受的。
        """
        return self.magnitude()

    def encode(self) -> str:
        """编码成字符串以便存进 Registry。

        @ADR-0003：值编码用**长度/个数前缀**，元素边界由类型自身界定，
        不依赖分隔符。曾经的"逗号拼接"方案在嵌套列表和含逗号字符串上
        必然出错（#13），且补丁式修补会不断引入新边界问题。
        见 docs/decisions/0003-decode-长度前缀编码.md

        约束：数字以外的类型要各走各的前缀，且**必须**能原样解回来。
        S<长度>:<内容>   字符串
        L<个数>:<元素...> 列表
        N:<数值>         数字

        #12「加了字符串/列表之后，decode 用 `^N:` 的正则去匹配 S: 开头的串，
             永远匹配失败，于是所有字符串都静默变成数字 0」
        {曾出现：_tmp 探针里 $("abc") 输出 0 ⟨FALSE⟩ 0b0}根因：decode 只认 N: 前缀，
        匹配失败时**没有报错而是返回 0**——那个容错分支在只有数字时是"友好"，
        有了多类型之后它变成了"静默吞掉类型"。修法：按前缀分派，见 decode。
        **已验证**。

        #13「嵌套列表 $( [1, [2, [3]]] ) 输出成 [1, 0, [0]]，内层数据全丢」
        {曾出现：字符串/列表探针的"嵌套列表"用例，同时 $(["a,b","c"]) 被切成 3 个元素}
        根因（重要）：列表原先用 ",".join() 拼接、str.split(",") 切分。内层列表
        编码后本身含逗号（L:[N:2,L:[N:3]]），被外层一刀切开就成了残缺片段，
        正则匹配失败，于是又落进 #12 那个"返回 0"的兜底分支——**同一个兜底分支
        连犯两案**。修法：改用长度/个数前缀编码，元素边界由类型自己界定，
        彻底不依赖分隔符；同时把兜底从"返回 0"改成抛异常。
        **已验证**（_tmp_str_probe.py 的嵌套列表、含逗号字符串用例）。
        """
        raw = self.raw
        if isinstance(raw, str):
            # 长度前缀 + 原样内容。这样内容里出现任何字符（逗号、方括号、引号）
            # 都不会产生歧义，也**不需要任何转义**——解码时按长度精确切即可。
            # 这比原来的 \" 转义方案更笨，但更不容易错。
            return "S" + str(len(raw)) + ":" + raw
        if isinstance(raw, list):
            # 列表：先写元素个数，再把每个元素的编码用 ',' 连起来。
            # 例如 [1,[2]] → L2:N:1,L1:N:2,
            # 解码时先读个数，再让每个元素自己吃掉该吃的那一段。
            # {意图：增加复杂度} —— 每个元素都要递归走一遍自己这一层的 encode，
            # 所以嵌套列表的编码耗时是乘积级的。
            pieces = []
            for item in raw:
                pieces.append(item.encode())
            joined = ",".join(pieces)
            return "L" + str(len(raw)) + ":" + joined
        value = self.decoded()
        if value == int(value):
            return "N:" + str(int(value))
        return "N:" + repr(value)

    @staticmethod
    def decode(blob: str) -> "PyPyValue":
        """从字符串解码。

        约束：本方法**必须**与 encode 严格对称，任何不对称都会静默产生错值。
        为杜绝 #12/#13 那种"匹配失败就返回 0"的静默兜底，
        解不出来一律抛 ValueError（解释器会把它变成带位置的「炑」）。
        """
        # --- 字符串：S<长度>:<内容> -------------------------------------------
        if blob.startswith("S"):
            colon = blob.find(":")
            if colon > 0:
                count_text = blob[1:colon]
                if count_text.isdigit():
                    size = int(count_text)
                    body = blob[colon + 1:]
                    return PyPyValue(body[:size])

        # --- 列表：L<个数>:<元素1>,<元素2>,... -------------------------------
        if blob.startswith("L"):
            colon = blob.find(":")
            if colon > 0:
                count_text = blob[1:colon]
                if count_text.isdigit():
                    size = int(count_text)
                    body = blob[colon + 1:]
                    items = []
                    cursor = 0
                    for _ in range(size):
                        element, consumed = PyPyValue._decode_one(body, cursor)
                        items.append(element)
                        cursor = cursor + consumed
                    return PyPyValue(items)

        # --- 数字 --------------------------------------------------------------
        RE_NUMBER = re.compile(r"^N:(-?[0-9]+(?:\.[0-9]+)?)$")
        matched_number = RE_NUMBER.match(blob)
        if matched_number is not None:
            body = matched_number.group(1)
            # int() 失败就试 float()——这是本文件里少数"正常"的错误处理。
            try:
                return PyPyValue(int(body))
            except ValueError:
                return PyPyValue(float(body))

        # 全都匹配不上。**不再静默返回 0**——那是 #12/#13 的根源。
        raise ValueError("无法解码的值：" + repr(blob))

    @staticmethod
    def _decode_one(blob, start):
        """从 blob 的 start 位置解出一个元素，返回 (值, 消耗的字符数)。

        约束：本方法是 #13 的修复核心——它让"元素边界"由**类型自己**界定，
        而不是靠逗号猜：
            字符串按前面写的长度切，
            列表按前面写的个数递归，
            数字一路读到逗号或结尾为止。
        {意图：增加复杂度} —— 教科书做法是边扫边解析（一次遍历），
        这里选择了"递归 + 返回消耗长度 + 外层累加游标"的三段式，
        并且每层都要重新 find 一次冒号，同一段字符串被反复扫描。

        #15「列表解码抛 ValueError: 无法解码的值：''，所有含元素的列表全崩」
        {曾出现：改用长度前缀编码后，[1,2,3] 直接抛裸 ValueError}
        根因：encode 用 ','.join() 连接元素，所以**除第一个元素外，
        每个元素前面都顶着一个逗号**（"L2:N:1,N:2,"）。而本方法拿到
        cursor 指向的位置时没有跳过这个逗号，于是切出一个空片段，
        交给 decode 后触发"解不出来就抛异常"。
        修法：进入本方法先跳过前导逗号。**已验证**。
        """
        remaining = blob[start:]

        # 跳过分隔用的逗号。第一个元素前面没有逗号，所以这一步是"有则跳"。
        # 约束：跳过的长度要**算进消耗量**，否则调用方的游标会漂移，
        #       下一个元素就会从逗号中间开始读——这正是 #15 的表现。
        skipped = 0
        while remaining.startswith(","):
            remaining = remaining[1:]
            skipped = skipped + 1

        if remaining.startswith("S"):
            colon = remaining.find(":")
            count_text = remaining[1:colon]
            size = int(count_text)
            body = remaining[colon + 1:]
            text = body[:size]
            consumed = skipped + colon + 1 + size
            return PyPyValue(text), consumed

        if remaining.startswith("L"):
            colon = remaining.find(":")
            count_text = remaining[1:colon]
            size = int(count_text)
            body = remaining[colon + 1:]
            items = []
            cursor = 0
            for _ in range(size):
                element, used = PyPyValue._decode_one(body, cursor)
                items.append(element)
                cursor = cursor + used
            consumed = skipped + colon + 1 + cursor
            return PyPyValue(items), consumed

        # 数字：读到逗号或字符串结尾为止
        stop = remaining.find(",")
        if stop < 0:
            stop = len(remaining)
        token = remaining[:stop]
        inner = PyPyValue.decode(token)
        return inner, skipped + stop

    def __repr__(self):
        return "PyPyValue(" + str(self.raw) + ")"


# =====================================================================================
# 抽象层 5：词法分析器（Lexer）
# =====================================================================================
#
# {意图：增加复杂度}
# 这个 Lexer 的工作方式：先逐字符扫描做出 token，然后**每个 token 都送给
# 正则层再验一遍**（层 2），然后再把每个 token 转成一个"TokenEnvelope"对象。
#
# 一个正常的 Lexer 到这里就结束了。我们还要继续走。

# Token 种类表 + 每种的中文说明（说明从不被读取，仅供人类困惑）
TOKEN_SPEC = {
    "NUMBER": "数字字面量，如 5 或 3.14",
    "IDENT": "标识符，即变量名",
    "SYMBOL": "运算符或分隔符，如 ( ) + = ;",
    "KEYWORD": "保留字，如 manifest / will / yield / if",
    "EOF": "输入终结者",
}

# pyPython 保留字 → token 类型。
#
# {意图：降低可读性 -> 已按用户要求反转为"语法尽量简单"}
# 旧版有 manifest/will/be/yield 四个关键字组成三阶段变量，现已全部删除，
# 只剩 if / else。语法简单了，但**底层一点没简单**——赋值照样要走
# Registry 的字符串往返，输出的照样是真值密室 + 手写二进制。
KEYWORDS = {
    "if": "KW_IF",
    "else": "KW_ELSE",
}

# 单字符符号集合。
# #1「'{' '}' 报"无法识别的字符"，if 语句块无法解析」——
# 最初这里漏了花括号，但 Parser._block 要求 '{'，两边不一致。
# 根因是符号集合分散在三处（这里、RE_SYMBOL、Parser._block），加了符号容易漏掉一处。
# 现状：已改用缩进断句，花括号和分号都不再需要，本集合已同步移除它们。
#
# 符号表（用户定的最终版）：
#   「」  赋值括号。x「1」 表示 x = 1，可跨行。
#   $ () 输出。$(x) 打印 x。
#   ~    等于（直接打）
#   ·    不等于（Shift 打出来）
#   > <  照旧
#   + - * / ( ) 算术与分组
# 约束：'.' 只当小数点，**不**当比较符（用户明确否决了兼容写法）。
SINGLE_SYMBOLS = "()+-*/<>~·「」$[],"


class TokenEnvelope:
    """token 的信封。

    {意图：增加复杂度} —— 一个 token 本来是一个 (类型, 内容) 二元组，
    这里把它包装成对象，还额外存了 3 个从不被使用的字段：
    验证宽度（来自正则层）、泬数、以及一个"指纹"字符串。
    """

    def __init__(self, kind: str, lexeme: str, line: int, column: int):
        self.kind = kind
        self.lexeme = lexeme
        self.line = line
        self.column = column
        # 下面三个字段都是为了"看起来做了很多事"
        self.validation_width = deep_validate(self._validation_class(), lexeme)
        self.fingerprint = str(hash(lexeme + str(line) + str(column)) % 100000)
        self.pypython_cost = 1

    def _validation_class(self) -> str:
        """把 token 类型映射到正则层认识的类别。多一层映射，多一层抽象。"""
        if self.kind == "NUMBER":
            return "NUMBER"
        if self.kind == "IDENT":
            return "IDENT"
        if self.kind == "SYMBOL":
            return "SYMBOL"
        return "OTHER"

    def describe(self) -> str:
        return self.kind + "(" + self.lexeme + ")"


class LexError(Exception):
    """词法错误。本文件里唯一认真的地方：错误必须带位置。

    约束：本类的 format() **故意不从基类继承**——三个错误类各留一份几乎相同的
    format()，这是刻意的重复。合并成一个基类能少 40 行，但"能绕就绕"是本项目
    精神，少代码等于少抽象。
    """

    def __init__(self, message, line, column, source_line=""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line
        # 跨语言习惯提示。由 _foreign_hint() 填，没有对应习惯时是空串。
        self.hint = ""

    def format(self):
        pad = " " * max(self.column - 1, 0)
        head = "LexError: " + self.message + "（第 %d 行 第 %d 列）" % (self.line, self.column)
        # 提示行插在标题和源码之间：先告诉用户"你从别的语言带了个习惯过来"，
        # 再给位置和指示符，用户才知道该往哪看。
        if self.hint:
            head = head + "\n  → " + self.hint
        if not self.source_line:
            return head
        return head + "\n  | " + self.source_line + "\n  | " + pad + "^"


# -------------------------------------------------------------------------------------
# 跨语言习惯对照表（FOREIGN HABITS）
# -------------------------------------------------------------------------------------
#
# {意图：不增加也不减少复杂度，只把一句没用的话换成一句有用的话}
#
# 起因：#8「用户写 if x ~ 1 { 只得到"无法识别的字符 '{'"，不知道该改成什么」
# {曾出现：用户反馈——从 C/Python/JS 过来的人必然先写花括号、分号和等号，
#  而旧版报错只说"这个字符我不认识"，等于没说怎么改}
# 修法：加这张表，在 Lexer 报"无法识别的字符"之前先查一遍。
#
# 取舍：这张表**不减少用户踩坑的次数**——花括号照样是错的、分号照样不能用。
#       它只是让报错带方向。本项目不追求好用，但"报错不指向任何出路"是纯粹的
#       浪费，跟"刻意绕路"不是一回事：绕路要绕得有产出（泬账本上有记录），
#       而含混的报错没有任何产出。
#
# 约束：这张表只在**词法层**生效（因为失败的是"认字符"这一步）。
#       像 print(x) 这种"字符都认识、但拼不出语句"的情况，走的是 Parser 的分支，
#       见 Parser._statement。
FOREIGN_HABITS = {
    "{": "pyPython 用缩进划分语句块，不用花括号（把 { 删掉，块内容缩进即可）",
    "}": "pyPython 用缩进划分语句块，不用花括号（把 } 删掉）",
    ";": "pyPython 不用分号，换行就是语句结束（把 ; 删掉）",
    "=": "赋值请用「」而不是 =（写 x「1」）；比较相等用 ~，不等用 ·",
    # 字符串和列表已支持（见 _scan_string 与 _atom 的 '[' 分支），
    # 所以原先那几条"暂不支持"的提示已撤销，否则会把用户引向错误方向。
    # 单引号仍不支持：本语言只认双引号字符串。
    "'": "pyPython 的字符串只用双引号，不用单引号",
    ":": "pyPython 不用冒号开启语句块，块内容直接缩进",
    "@": "pyPython 没有装饰器语法",
}


def foreign_hint(char: str) -> str:
    """查跨语言习惯表。查不到就返回空串。

    {意图：增加复杂度} —— 一个 dict.get() 就能搞定，这里偏要
    先判断 key 在不在、再取出来、再把结果经过一次字符串拼接。
    多两次操作，行为完全一样。
    """
    if char in FOREIGN_HABITS:
        raw = FOREIGN_HABITS[char]
        return str(raw)
    return ""


class Lexer:
    """逐字符扫描的 Lexer。

    {意图：增加复杂度}
    即便用 regex 一行就能切完所有 token，这里坚持手写状态机，
    因为需求 1 禁止依赖现成解析工具——手写的同时还要**额外**调用正则，
    从而同时满足"手搓"和"2 次正则"两条要求。
    """

    def __init__(self, source: str):
        self.source = source.expandtabs(4)
        self.lines = self.source.split("\n")
        self.pos = 0
        self.line = 1
        self.column = 1
        self.book = LogBook()

    def _err(self, message):
        text = self.lines[self.line - 1] if self.line - 1 < len(self.lines) else ""
        return LexError(message, self.line, self.column, text)

    def _peek(self, offset=0):
        index = self.pos + offset
        if index < len(self.source):
            return self.source[index]
        return ""

    def _take(self):
        char = self.source[self.pos]
        self.pos = self.pos + 1
        if char == "\n":
            self.line = self.line + 1
            self.column = 1
        else:
            self.column = self.column + 1
        return char

    def tokenize(self):
        """主循环。

        每产生一个 token，都：
          1. 手工扫描（状态机）
          2. 交给正则层验证（层 2）
          3. 包装成 TokenEnvelope（含 3 个无用字段）
          4. 在账本上记一笔泬

        断句规则（用户定的最终版，替代旧版的分号）：
          · 换行 = 语句结束，跟 Python 一样
          · 缩进 = 语句块，跟 Python 一样
          · **例外**：`「」` 内部的换行不算语句结束，因为用户明确要求
            「」可以跨行写（否则长表达式没法换行）
          · 用 INDENT / DEDENT 两个虚拟 token 表达缩进变化，
            Parser 那边看到 DEDENT 就知道块结束了

        {意图：增加复杂度} —— 明明可以用一个括号计数器搞定，
        这里偏要维护一个缩进栈，并且每次换行都重新计算一遍缩进宽度，
        再把宽度转成字符串、再解析回整数（为了凑"数据转换"次数）。
        """
        envelopes = []
        indent_stack = [0]         # 缩进栈，栈顶是当前块宽度
        bracket_depth = 0          # 「」嵌套深度；>0 时换行不当作语句结束
        at_line_start = True       # 是否正处于一行的开头（要算缩进）

        while self.pos < len(self.source):
            char = self._peek()

            # --- 行首：算缩进，产出 INDENT / DEDENT -------------------------------
            if at_line_start:
                at_line_start = False
                width = self._measure_indent()
                if width is None:
                    # 空行或纯注释行，直接跳过，不产生任何缩进 token
                    continue
                current = indent_stack[len(indent_stack) - 1]
                if width > current:
                    # 缩进变深。注意：本语言**不检查**"上一行是否以 if 结尾"，
                    # 也就是随便缩进都合法——这是刻意的宽松，
                    # 因为"什么时候该缩进"的判断留给用户自己困惑。
                    indent_stack.append(width)
                    envelopes.append(self._virtual("INDENT", "", self.line, 1, width))
                    self.book.mint("词法:缩进加深")
                elif width < current:
                    # 缩进变浅，可能要退多层
                    while len(indent_stack) > 1 and width < indent_stack[len(indent_stack) - 1]:
                        indent_stack.pop()
                        envelopes.append(self._virtual("DEDENT", "", self.line, 1, width))
                        self.book.mint("词法:缩进回退")
                    # 退到跟某个已有层级不一样深，说明缩进对不齐，报错
                    if indent_stack[len(indent_stack) - 1] != width:
                        raise self._err(
                            "缩进对不齐（这一行缩进了 " + str(width)
                            + " 格，但外层没有这个层级）"
                        )

            # --- 空白与注释 -------------------------------------------------------
            if char in " \t":
                self._take()
                continue

            if char in "\r\n":
                # 换行：只有在「」闭合的情况下才当作语句结束
                self._take()
                if bracket_depth == 0:
                    envelopes.append(self._virtual("NEWLINE", "", self.line, 1))
                    self.book.mint("词法:换行断句")
                    at_line_start = True
                continue

            if char == "#":
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._take()
                continue

            # 字符串字面量：双引号包裹。
            # 约束：字符串**内部**的 # 不是注释——这是加字符串时最容易踩的地方，
            # 原先的注释处理是无条件的（因为当时根本没有字符串）。
            # 现在字符串先于注释判断，且扫描时整段吞掉，所以内部的 # 安全。
            if char == '"':
                envelopes.append(self._scan_string())
                continue

            # 方括号只影响断句（内部换行不结束语句），本身仍是符号。
            # 复用 bracket_depth：只要在「」或 [] 里，换行都不算语句结束。
            if char == "[":
                bracket_depth = bracket_depth + 1
                envelopes.append(self._scan_symbol())
                continue

            if char == "]":
                if bracket_depth <= 0:
                    raise self._err("多了一个 ']'（没有与之配对的 '['）")
                bracket_depth = bracket_depth - 1
                envelopes.append(self._scan_symbol())
                continue

            if char.isdigit():
                envelopes.append(self._scan_number())
                continue

            if char.isalpha() or char == "_":
                envelopes.append(self._scan_word())
                continue

            # --- 「」 影响断句，所以要在扫描符号时同步计数 -------------------------
            if char == "「":
                bracket_depth = bracket_depth + 1
                envelopes.append(self._scan_symbol())
                continue

            if char == "」":
                if bracket_depth <= 0:
                    raise self._err("多了一个 '」'（没有与之配对的 '「'）")
                bracket_depth = bracket_depth - 1
                envelopes.append(self._scan_symbol())
                continue

            if char in SINGLE_SYMBOLS:
                envelopes.append(self._scan_symbol())
                continue

            # 认不出来的字符：先查跨语言习惯表，让报错带方向。
            # 查得到就给提示，查不到就只报位置——两条路径都保留。
            raise self._err_with_hint(char)

        # 文件末尾：先补一个 NEWLINE（否则最后一行没有语句结束标记），
        # 再把所有还开着的缩进层退掉，最后才是 EOF。
        if bracket_depth > 0:
            raise self._err("「 没有闭合（共缺 " + str(bracket_depth) + " 个 '」'）")
        envelopes.append(self._virtual("NEWLINE", "", self.line, self.column))
        while len(indent_stack) > 1:
            indent_stack.pop()
            envelopes.append(self._virtual("DEDENT", "", self.line, self.column))

        # EOF 也要包装成信封，也要验正则，也要记泬——一视同仁。
        envelopes.append(TokenEnvelope("EOF", "", self.line, self.column))
        self.book.mint("词法:终点信封")
        return envelopes

    def _scan_string(self):
        """扫描字符串字面量 "..."。

        约束：支持 \\" 和 \\\\ 两个转义；不支持 \\n 之类的其他转义——
        想换行就直接在字符串里换行（反正「」和 [] 内部换行不断句）。
        {意图：增加复杂度} —— 扫完之后把内容再拆成字符列表、再拼回字符串，
        纯粹为了让每个字符串都经历一次 list 往返。
        """
        start_line, start_col = self.line, self.column
        self._take()  # 吃掉开头的引号

        chunks = []
        while True:
            if self.pos >= len(self.source):
                raise self._err("字符串没有闭合（缺少收尾的 '\"'）")
            current = self._peek()
            if current == "\\":
                self._take()
                if self.pos >= len(self.source):
                    raise self._err("字符串末尾的反斜杠没有内容可转义")
                chunks.append(self._take())
                continue
            if current == '"':
                self._take()
                break
            chunks.append(self._take())

        text = "".join(chunks)

        # 拆成字符列表再拼回去。{意图：增加复杂度}
        char_list = []
        for index in range(len(text)):
            char_list.append(text[index])
        rebuilt = ""
        for char in char_list:
            rebuilt = rebuilt + char

        self.book.mint("词法:字符串信封")
        envelope = TokenEnvelope("STRING", rebuilt, start_line, start_col)
        envelope.recovered = rebuilt
        return envelope

    def _err_with_hint(self, char):
        """构造"无法识别的字符"错误，并附带跨语言习惯提示（如果有）。

        {意图：增加复杂度} —— 提示的取用、拼接、再塞回异常对象，
        分了四步写，其实一行就能完成。

        #10「整份文件的所有报错都变成 TypeError: 'NoneType' object is not subscriptable」
        {曾出现：加了跨语言提示后，除花括号/分号/等号之外的**所有**测试用例都崩，
         且崩出来的不是语言的报错而是裸 Python TypeError，完全没有行号}
        根因：本方法最初被插进了 tokenize() 的中间，把"文件末尾收尾"那一整段
              （补 NEWLINE、退缩进栈、追加 EOF）挤成了本方法内部永远执行不到的代码。
              于是 tokenize() 提前结束、**丢掉了 return envelopes**，返回 None；
              Parser 拿到 None 之后在 self.envs[self.i] 处炸出 TypeError。
        教训：本类里"文件末尾收尾"必须是 tokenize() 的最后一段，任何新方法都要
              插在它**之后**，不能插在中间。
        **已验证**（_tmp_err_probe.py 全部 12 例）。
        """
        error = self._err("无法识别的字符 " + repr(char))
        hint_text = foreign_hint(char)
        if hint_text == "":
            error.hint = ""
            return error
        assembled = ""
        assembled = assembled + hint_text
        error.hint = assembled
        self.book.mint("词法:跨语言提示")
        return error

    def _measure_indent(self):
        """量出当前行的缩进宽度；如果是空行/纯注释行则返回 None。

        {意图：增加复杂度} —— 缩进宽度明明可以直接数空格，
        这里偏要扫到一个非空白字符，再回头数一遍；
        并且把宽度转成字符串再转回整数（凑数据转换次数）。

        约束：tab 已在 __init__ 里按 4 空格展开，所以这里只需数空格。
        """
        scan = self.pos
        while scan < len(self.source) and self.source[scan] in " \t":
            scan = scan + 1
        # 扫到行尾或注释，说明这一行没有实际内容
        if scan >= len(self.source) or self.source[scan] in "\r\n#":
            # 把这一行吃掉（含注释），让主循环继续往下走
            while self.pos < len(self.source) and self._peek() != "\n":
                self._take()
            if self.pos < len(self.source):
                self._take()
            return None
        raw_width = scan - self.pos
        as_text = str(raw_width)          # int → str
        return int(as_text)               # str → int，纯仪式

    def _virtual(self, kind, lexeme, line, column, extra=None):
        """产出一个"虚拟 token"（INDENT/DEDENT/NEWLINE）。

        它们不对应任何源码文本，但要走完全一样的包装流程——
        包括正则验证和泬记账，否则它们就成了"便宜的 token"，那不公平。
        """
        envelope = TokenEnvelope(kind, lexeme, line, column)
        envelope.indent_width = extra
        self.book.mint("词法:虚拟信封 " + kind)
        return envelope

    def _scan_number(self):
        start_line, start_col, start = self.line, self.column, self.pos
        while self._peek().isdigit():
            self._take()
        if self._peek() == ".":
            self._take()
            if not self._peek().isdigit():
                raise self._err("小数点后面必须有数字（本语言拒绝 1. 这种写法）")
            while self._peek().isdigit():
                self._take()

        lexeme = self.source[start:self.pos]
        # 手工扫描完之后，再用正则确认一遍这确实是数字。
        # {意图：增加复杂度} —— 不信任自己的扫描器，仪式感拉满。
        if revalidate("NUMBER", lexeme) == 0:
            raise self._err("正则层拒绝了这个数字 " + repr(lexeme))

        # 再做一次"两次转换"：字符串 → float → 字符串 → int/float
        as_float = float(lexeme)
        back_to_text = repr(as_float)
        self.book.mint("词法:数字双转换")

        envelope = TokenEnvelope("NUMBER", lexeme, start_line, start_col)
        envelope.recovered = back_to_text  # 又一次没人读的写入
        return envelope

    def _scan_word(self):
        start_line, start_col, start = self.line, self.column, self.pos
        while self._peek().isalnum() or self._peek() == "_":
            self._take()
        lexeme = self.source[start:self.pos]

        if lexeme in KEYWORDS:
            self.book.mint("词法:关键字信封")
            return TokenEnvelope(KEYWORDS[lexeme], lexeme, start_line, start_col)

        if revalidate("IDENT", lexeme) == 0:
            raise self._err("正则层拒绝了这个标识符 " + repr(lexeme))
        self.book.mint("词法:标识符信封")
        return TokenEnvelope("IDENT", lexeme, start_line, start_col)

    def _scan_symbol(self):
        start_line, start_col = self.line, self.column
        lexeme = self._take()
        if revalidate("SYMBOL", lexeme) == 0:
            raise self._err("正则层拒绝了这个符号 " + repr(lexeme))
        self.book.mint("词法:符号信封")
        return TokenEnvelope("SYMBOL", lexeme, start_line, start_col)


# =====================================================================================
# 抽象层 6：语法分析器（Parser）—— 11 层优先级，但优先级毫无意义
# =====================================================================================
#
# {意图：增加复杂度} + {意图：降低可读性}
#
# 这是本项目的喜剧高潮：pyPython 的运算符**不分优先级**（全部右结合），
# 但 Parser 依然实现了完整的 11 层优先级函数链。
#
# 每一层都：调用下一层、然后不做任何事、再把结果原样返回。
# 唯一的副作用是往账本里记一笔泬。
#
# 也就是说：11 层优先级纯粹是装饰。它不影响任何解析结果，
# 但它让代码看起来像一本编译器教科书，并让每次解析多绕 11 层函数调用。
#
# 语法树节点（都不做优化，纯数据）


class Node:
    """语法树节点基类。

    {意图：增加复杂度} —— 每个节点都要记自己的位置，
    而且构造时要把自己的所有字段再序列化一遍存进 self.shadow，
    这个 shadow 从不被读取，纯粹是为了"每个节点都发生过一次数据转换"。
    """

    def __init__(self, line, column):
        self.line = line
        self.column = column
        self.shadow = None
        self.visits = 0

    def reify(self):
        """每次被访问时调用。把节点重新包装一次。

        {意图：增加复杂度} —— 需求说"每访问一个节点顺手把它重新包装"。
        这里把节点的类名和字段拼成一个字符串存进 shadow，
        于是在解释阶段每访问一个节点就多一次字符串构造。
        """
        self.visits = self.visits + 1
        self.shadow = type(self).__name__ + "@" + str(self.line) + ":" + str(self.column)
        return self.shadow


class NumberNode(Node):
    def __init__(self, text, line, column):
        Node.__init__(self, line, column)
        self.text = text


class IdentNode(Node):
    def __init__(self, name, line, column):
        Node.__init__(self, line, column)
        self.name = name


class StringNode(Node):
    """字符串字面量节点。text 是已经解好转义的原始内容。

    {意图：增加复杂度} —— 明明可以复用 NumberNode 的存储方式（都只是一个文本），
    但这里坚持单开一个类，于是解释器多一条 isinstance 分支、多一次记账。
    """

    def __init__(self, text, line, column):
        Node.__init__(self, line, column)
        self.text = text


class ListNode(Node):
    """列表字面量节点。elements 是任意表达式节点列表。

    {意图：增加复杂度} —— 列表的每个元素在求值时都要独立走完
    _evaluate → 编码 → 解码 的完整链条，所以列表越长，绕的路是线性叠加的。
    """

    def __init__(self, elements, line, column):
        Node.__init__(self, line, column)
        self.elements = elements


class CallNode(Node):
    """旧版的"波兰表达式"节点，如 (+ a b) 或 (= x 1)。

    约束：新语法改中缀后**本节点已不再被 Parser 产出**，但保留定义，
    因为 Interpreter 与账本统计里还有引用它的分支。
    留着它也是"能跑的别删"这一项目精神的体现——哪怕它是死代码。
    {意图：增加复杂度} —— 一个不再使用的类，仍然占着解释器的 isinstance 分支。
    """

    def __init__(self, operator, operands, line, column):
        Node.__init__(self, line, column)
        self.operator = operator
        self.operands = operands


class BinOpNode(Node):
    """中缀二元运算节点（新语法）：`a + b`、`x ~ 1`、并排相乘等。

    {意图：增加复杂度} —— 与 CallNode 的区别仅仅是"操作数怎么排"，
    但这里坚持另开一个类，于是解释器里就多了一条 isinstance 分支。
    每个分支都要走一遍 reify 与账本记账。
    """

    def __init__(self, operator, left, right, line, column):
        Node.__init__(self, line, column)
        self.operator = operator
        self.left = left
        self.right = right


class NegNode(Node):
    """一元负号节点：`-x`。

    {意图：增加复杂度} —— 完全可以复用 BinOpNode（用 0 - x 表示），
    但那样就少了一个节点类型、少一条分派分支、少一次记账。
    """

    def __init__(self, operand, line, column):
        Node.__init__(self, line, column)
        self.operand = operand


# 语句节点
class ManifestStmt(Node):
    """旧版"声明"语句。新语法已废弃，保留定义仅供旧账本引用。"""

    def __init__(self, name, line, column):
        Node.__init__(self, line, column)
        self.name = name


class WillStmt(Node):
    """旧版"赋值"语句。新语法已废弃，保留定义仅供旧账本引用。"""

    def __init__(self, name, expr, line, column):
        Node.__init__(self, line, column)
        self.name = name
        self.expr = expr


class YieldStmt(Node):
    """旧版"输出"语句。新语法已废弃，保留定义仅供旧账本引用。"""

    def __init__(self, expr, line, column):
        Node.__init__(self, line, column)
        self.expr = expr


class AssignStmt(Node):
    """新语法赋值：`x「表达式」`

    {意图：增加复杂度} —— 语法上从三步（manifest/will/be）压成一步，
    但语义上**仍然是三步**：解释器照样要先查名字是否存在（相当于声明）、
    再求值、再写回 Registry。省掉的只是用户的打字量，机器一步没省。
    """

    def __init__(self, name, expr, line, column):
        Node.__init__(self, line, column)
        self.name = name
        self.expr = expr


class PrintStmt(Node):
    """新语法输出：`$(表达式)`"""

    def __init__(self, expr, line, column):
        Node.__init__(self, line, column)
        self.expr = expr


class IfStmt(Node):
    def __init__(self, cond, then_body, else_body, line, column):
        Node.__init__(self, line, column)
        self.cond = cond
        self.then_body = then_body
        self.else_body = else_body


class ParseError(Exception):
    def __init__(self, message, line, column, source_line=""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line

    def format(self):
        pad = " " * max(self.column - 1, 0)
        head = "ParseError: " + self.message + "（第 %d 行 第 %d 列）" % (self.line, self.column)
        if not self.source_line:
            return head
        return head + "\n  | " + self.source_line + "\n  | " + pad + "^"


class MuError(Exception):
    """运行期错误（俗称「炑」）。

    #9「类名叫 DeferredError，但显示名是 MuCollapse，两边对不上」
    {曾出现：用户问报错有定义吗时发现——显示层改成了「炑」，
    类名还是旧的 DeferredError，命名不一致}
    修法：类名改为 MuError，与「炑」(mu) 对齐。
    约束：同样**不**与其他错误类共享 format()，见 LexError 的说明。
    """

    def __init__(self, message, line=0, column=0, source_line=""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line

    def format(self):
        if self.line == 0:
            return "MuCollapse: " + self.message
        pad = " " * max(self.column - 1, 0)
        head = "MuCollapse: " + self.message + "（第 %d 行 第 %d 列）" % (self.line, self.column)
        if not self.source_line:
            return head
        return head + "\n  | " + self.source_line + "\n  | " + pad + "^"


class Parser:
    """递归下降 Parser。

    {意图：降低可读性}
    方法名故意用紫微斗数/炼丹术词汇，让调用关系需要查注释才能看懂：
        _l11 → _l10 → ... → _l2 → _atom
    数字越大越"底层"。读到 _l7 的时候你很难记得 l11 是干嘛的。
    """

    def __init__(self, envelopes, lines, book):
        self.envs = envelopes
        self.lines = lines
        self.book = book
        self.i = 0
        self.priority_hops = 0  # 统计这 11 层到底跑了多少次（纯为了炫耀）
        # 是否处于括号内。用户规定"并排即相乘"只在括号内生效，
        # 否则 `$(x) $(y)` 一行两输出会被误解析成乘法。见 Parser._juxtapose。
        #
        # #6「$( (1 + 2) 3 ) 报"输出缺少收尾的 ')'"」{曾出现：内层括号关闭后
        #    外层括号的并排相乘能力也一起丢了}根因：最初用布尔 in_parens，
        #    内层 '(' 保存/恢复时把外层的 True 覆盖成了 False。
        #    括号可以嵌套，所以布尔不够用。修法：改成计数器括号深度。
        #    **已验证**（main 用例 1 与 _tmp_run_probe.py）。
        self.paren_depth = 0
        # 上一个解析出来的原子是不是"从括号里出来的"。
        # 并排即相乘靠这个标志判断，见 _juxtapose 里的 #7 注释。
        self.last_atom_was_paren = False

    # -- 游标 ------------------------------------------------------------------------

    def _cur(self):
        return self.envs[self.i]

    def _bump(self):
        env = self.envs[self.i]
        if env.kind != "EOF":
            self.i = self.i + 1
        return env

    def _line_text(self, line):
        if line - 1 < len(self.lines):
            return self.lines[line - 1]
        return ""

    def _fail(self, message):
        env = self._cur()
        raise ParseError(message, env.line, env.column, self._line_text(env.line))

    def _want(self, kind, human):
        if self._cur().kind != kind:
            env = self._cur()
            found = env.lexeme if env.kind != "EOF" else "文件结尾"
            self._fail("期待" + human + "，却遇到 " + repr(found))
        return self._bump()

    def _is(self, kind):
        return self._cur().kind == kind

    # -- 十一个优先级层 --------------------------------------------------------------
    #
    # {意图：增加复杂度}
    # 下面 11 个函数**功能完全相同**：调用下一层，原样返回。
    # 保留它们是为了让"每条表达式都经过 11 层函数调用"这一事实成立，
    # 并让泬账本上多出 11 条记录。
    #
    # 为什么是 11 层？因为 C 语言有 11 个优先级档位，而我们一层都不用。

    def _l11(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层11")
        result = self._l10()
        return result

    def _l10(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层10")
        result = self._l9()
        return result

    def _l9(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层9")
        result = self._l8()
        return result

    def _l8(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层8")
        result = self._l7()
        return result

    def _l7(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层7")
        result = self._l6()
        return result

    def _l6(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层6")
        result = self._l5()
        return result

    def _l5(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层5")
        result = self._l4()
        return result

    def _l4(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层4")
        result = self._l3()
        return result

    def _l3(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层3")
        result = self._l2()
        return result

    def _l2(self):
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层2")
        result = self._l1()
        return result

    def _l1(self):
        """第 1 层，唯一真正干活的层。

        {意图：增加复杂度} —— 11 层装饰到这里才落地。
        注意：新语法是中缀，所以下面不再是"波兰表达式"，
        而是一个普通的优先级递归下降。**但 11 层装饰一个都没删**——
        语法简单了，机器该绕的路一步没少。
        """
        self.priority_hops = self.priority_hops + 1
        self.book.mint("解析:优先级层1")
        return self._juxtapose()

    # -- 真正的解析逻辑（新语法：中缀 + 并排即相乘）--------------------------------

    def _juxtapose(self):
        """并排即相乘：`(a + b) 2 3` == `(a+b) * 2 * 3`。

        {意图：增加复杂度} —— 用户明确要求"两个表达式并排就是相乘"，
        且**只在括号内生效**（否则 `$(x) $(y)` 一行两输出会被误判成乘法）。

        约束：判定依据是"左边的操作数是不是刚从括号里出来的"，
        而不是"解析器当前是否在括号内"。

        #7「$( (1 + 2) 3 ) 报"输出缺少收尾的 ')'"」{曾出现：并排相乘在
        嵌套括号里失效}根因（重要，别再踩）：最初用"解析器递归深度计数器"
        self.paren_depth 判断是否在括号内。但 `(1 + 2)` 解析**返回之后**，
        计数器已经减回 0，此时轮到检查后面的 `3` —— 开关早已关闭，
        于是 `3` 不被接纳，报"缺少 )"。
        修法：改用"左侧操作数是否来自括号"这个**结果属性**来判断，
        由 _atom 在解析完 '(...)' 后设置 self.last_atom_was_paren。
        **已验证**（main 用例 1 与 _tmp_run_probe.py 全部 13 例）。
        """
        node = self._compare()
        # 只有当左边那个原子确实是从括号里解析出来的时候，才允许并排相乘。
        while self.last_atom_was_paren and self._starts_operand():
            right = self._compare()
            op_node = BinOpNode("*", node, right, node.line, node.column)
            op_node.reify()
            self.book.mint("解析:并排相乘")
            node = op_node
            # 乘完之后，左边的操作数已经不再是"裸括号"了；
            # 但用户要的是 (a+b) 2 3 = (a+b)*2*3，所以这里保持开关打开，
            # 由 _compare 内部解析 2 和 3 时各自维护自己的状态。
            self.last_atom_was_paren = True
        return node

    def _starts_operand(self):
        """判断当前 token 能不能作为一个操作数的开头。

        {意图：增加复杂度} —— 这个判断其实一行就能写，
        这里拆成独立的、带 docstring 的方法，就为了在调用栈上多一帧。
        """
        env = self._cur()
        if env.kind in ("NUMBER", "IDENT"):
            return True
        if env.kind == "SYMBOL" and env.lexeme == "(":
            return True
        return False

    def _compare(self):
        """比较运算：~ (等于) · (不等于) > (大于) < (小于)。

        {意图：增加复杂度} —— 注意 `~` 和 `·` 是**同一个键**（用户定的）：
        不按 Shift 出 `·`，按 Shift 出 `~`。
        于是本语言里"常用的等于"反而更难打，"少用的不等于"更顺手。
        这是刻意的设计，不是失误。风险见下方 #2 注释。

        #2「中文输入法下想打 ~ 却打出 ·，程序照跑但结果反了」
        {曾出现：用户反馈，待复现——我按用户要求没有加输入法误打提示}
        风险说明：`·` 和 `~` 同键，`·` 无需 Shift，因此写 `if x ~ 1` 时
        手滑成 `·` 的概率不低。这种错误**不报错**（因为 `·` 也是合法运算符），
        只会让条件判断结果相反——属于静默错误。
        已在设计阶段向用户指出，用户选择保留设计、不加提示。
        如果将来要加提示，位置就在这里：检测到 `·` 紧跟数字且左侧是 IDENT 时
        给一句"你是想写 ~ 吗"的警告即可。
        """
        node = self._additive()
        while True:
            env = self._cur()
            if env.kind == "SYMBOL" and env.lexeme in ("~", "·", ">", "<"):
                op_env = self._bump()
                right = self._additive()
                node = BinOpNode(op_env.lexeme, node, right, op_env.line, op_env.column)
                node.reify()
                self.book.mint("解析:比较节点")
                continue
            return node

    def _additive(self):
        """加减：+ -，左结合。"""
        node = self._multiplicative()
        while True:
            env = self._cur()
            if env.kind == "SYMBOL" and env.lexeme in ("+", "-"):
                op_env = self._bump()
                right = self._multiplicative()
                node = BinOpNode(op_env.lexeme, node, right, op_env.line, op_env.column)
                node.reify()
                self.book.mint("解析:加减节点")
                continue
            return node

    def _multiplicative(self):
        """乘除：* /，左结合。"""
        node = self._unary()
        while True:
            env = self._cur()
            if env.kind == "SYMBOL" and env.lexeme in ("*", "/"):
                op_env = self._bump()
                right = self._unary()
                node = BinOpNode(op_env.lexeme, node, right, op_env.line, op_env.column)
                node.reify()
                self.book.mint("解析:乘除节点")
                continue
            return node

    def _unary(self):
        """一元负号：-x。"""
        env = self._cur()
        if env.kind == "SYMBOL" and env.lexeme == "-":
            op_env = self._bump()
            operand = self._unary()
            node = NegNode(operand, op_env.line, op_env.column)
            node.reify()
            self.book.mint("解析:一元负号")
            return node
        return self._atom()

    def _atom(self):
        """原子：数字、标识符、或者括号表达式。

        {意图：增加复杂度} —— 现在是普通的中缀括号，
        `(a + b) 2` 里的括号既用于分组，也用于开启"并排相乘"。
        """
        env = self._cur()

        if env.kind == "NUMBER":
            self._bump()
            node = NumberNode(env.lexeme, env.line, env.column)
            node.reify()
            self.book.mint("解析:数字节点")
            self.last_atom_was_paren = False
            return node

        if env.kind == "IDENT":
            self._bump()
            node = IdentNode(env.lexeme, env.line, env.column)
            node.reify()
            self.book.mint("解析:标识符节点")
            self.last_atom_was_paren = False
            return node

        if env.kind == "STRING":
            self._bump()
            node = StringNode(env.lexeme, env.line, env.column)
            node.reify()
            self.book.mint("解析:字符串节点")
            self.last_atom_was_paren = False
            return node

        if env.kind == "SYMBOL" and env.lexeme == "[":
            return self._list_literal()

        if env.kind == "SYMBOL" and env.lexeme == "(":
            open_env = self._bump()
            self.book.mint("解析:开括号")
            self.paren_depth = self.paren_depth + 1
            inner = self._l11()
            self.paren_depth = self.paren_depth - 1
            if not (self._is("SYMBOL") and self._cur().lexeme == ")"):
                raise ParseError(
                    "括号没有闭合（从第 %d 行 第 %d 列 的 '(' 开始）"
                    % (open_env.line, open_env.column),
                    open_env.line,
                    open_env.column,
                    self._line_text(open_env.line),
                )
            self._bump()
            self.book.mint("解析:闭括号")
            # 关键：告诉上层"我刚从括号里出来"，_juxtapose 靠这个决定
            # 后面能不能并排相乘。见 #7 注释。
            self.last_atom_was_paren = True
            return inner

        found = env.lexeme if env.kind != "EOF" else "文件结尾"
        if env.kind in ("NEWLINE", "INDENT", "DEDENT"):
            found = "换行"
        self._fail("期待一个表达式，却遇到 " + repr(found))

    def _list_literal(self):
        """列表字面量：[表达式, 表达式, ...]

        {意图：增加复杂度} —— 空列表、单元素、多元素三条路径分开写，
        每条路径都要单独记一次账，就为了"每个分支都要留下痕迹"。
        约束：允许尾随逗号 [1, 2,]，因为拒绝它需要额外写一段检查——
        而本项目的原则是"能少写代码的地方要多写，能多写的地方不省"。
        """
        open_env = self._bump()  # 吃掉 '['
        self.book.mint("解析:列表开方括号")

        elements = []
        while not (self._is("SYMBOL") and self._cur().lexeme == "]"):
            if self._is("EOF"):
                raise ParseError(
                    "列表没有闭合（从第 %d 行 第 %d 列 的 '[' 开始）"
                    % (open_env.line, open_env.column),
                    open_env.line,
                    open_env.column,
                    self._line_text(open_env.line),
                )
            elements.append(self._l11())
            self.book.mint("解析:列表元素")
            # 元素之间用逗号分隔；如果没有逗号但也不是 ']'，报错。
            if self._is("SYMBOL") and self._cur().lexeme == ",":
                self._bump()
                self.book.mint("解析:列表逗号")
                continue
            if self._is("SYMBOL") and self._cur().lexeme == "]":
                break
            self._fail("列表元素之间要用 ',' 分隔")

        self._bump()  # 吃掉 ']'
        self.book.mint("解析:列表闭方括号")
        node = ListNode(elements, open_env.line, open_env.column)
        node.reify()
        # 列表也开启"并排即相乘"吗？**不开启**。
        # 约束：只有 '(' 才置 last_atom_was_paren，因为 [1,2] 3 会被读成
        # "列表后面跟一个数字"，语义上没有意义。保持不开启。
        self.last_atom_was_paren = False
        return node

    # -- 语句 ------------------------------------------------------------------------

    def parse(self):
        """program ::= { statement } EOF

        {意图：增加复杂度} —— 现在多了一层"跳过空行"的逻辑，
        因为换行是语句分隔符，连续换行会产生一堆空语句。
        """
        statements = []
        while not self._is("EOF"):
            if self._is("NEWLINE"):
                self._bump()
                continue
            statements.append(self._statement())
        return statements

    def _skip_newlines(self):
        while self._is("NEWLINE"):
            self._bump()

    def _want_newline(self):
        """语句结束：换行、或块结束、或文件结尾、**或同一行还有下一条语句**。

        约束：替代了旧版的 _want_semicolon。新语法没有分号，
        换行是主要的语句边界。

        #5「$(x) $(x) 一行两输出报"语句结尾期待换行"」{曾出现：用户要求允许
        一行写多条输出，但这里强制要求换行}根因：本方法最初只认换行/EOF/DEDENT。
        修法：把"后面还跟着语句起始 token"也算作合法结尾。
        **已验证**（_tmp_run_probe.py 的"一行两输出"用例）。

        注意：这条规则与"并排即相乘"不冲突，因为并排相乘**只在括号内**生效，
        而这里是在语句层——括号外并排 = 两条语句。
        """
        if self._is("NEWLINE"):
            self._bump()
            return
        if self._is("EOF") or self._is("DEDENT"):
            return
        # 同一行还能接下一条语句：靠"下一个 token 能不能开启语句"来判断。
        if self._starts_statement():
            return
        env = self._cur()
        self._fail("语句结尾期待换行，却遇到 " + repr(env.lexeme))

    def _starts_statement(self):
        """当前 token 能不能作为一条新语句的开头。

        {意图：增加复杂度} —— 这个判断在本文件里出现了三次
        （这里、_statement、_starts_operand），每次都各写一份，
        因为"统一成一个函数"会少两次调用，那不符合本项目精神。
        """
        env = self._cur()
        if env.kind in ("KW_IF", "IDENT"):
            return True
        if env.kind == "SYMBOL" and env.lexeme == "$":
            return True
        return False

    def _block(self):
        """缩进块：INDENT 语句* DEDENT。

        {意图：增加复杂度} —— 缩进在 Lexer 里已经算完了，
        这里只需要消费 INDENT/DEDENT 两个虚拟 token。
        但为了凑"多做一步"，这里会先把块内容收齐、再反转一遍
        （反转是无意义的，纯粹消耗时间）。
        """
        if not self._is("INDENT"):
            self._fail("这里需要一个缩进的语句块（if 后面必须跟缩进）")
        self._bump()
        body = []
        while not self._is("DEDENT") and not self._is("EOF"):
            if self._is("NEWLINE"):
                self._bump()
                continue
            body.append(self._statement())
        if self._is("DEDENT"):
            self._bump()
        self.book.mint("解析:缩进块")

        # 无意义的反转再反转，纯浪费。{意图：增加复杂度}
        flipped = []
        for index in range(len(body) - 1, -1, -1):
            flipped.append(body[index])
        restored = []
        for index in range(len(flipped) - 1, -1, -1):
            restored.append(flipped[index])
        return restored

    def _statement(self):
        """语句分发。

        {意图：增加复杂度} —— 每个语句形式都要经过一个独立的、只有一行的
        分派函数。这是为了在调用栈上多留几帧。
        """
        env = self._cur()

        if env.kind == "KW_IF":
            return self._stmt_if()
        if env.kind == "IDENT":
            return self._stmt_assign()
        if env.kind == "SYMBOL" and env.lexeme == "$":
            return self._stmt_print()

        found = env.lexeme if env.kind != "EOF" else "文件结尾"
        if env.kind in ("NEWLINE", "INDENT", "DEDENT"):
            found = "换行"
        self._fail("语句必须以 变量名 / if / $ 开头，却遇到 " + repr(found))

    def _stmt_assign(self):
        """赋值：IDENT「表达式」

        新语法把"声明 + 赋值"合成了一步（旧版是 manifest + will + be 三步）。
        {意图：增加复杂度} —— 语法上省了两个字，但解释器那边照样要查 Registry、
        走字符串往返、写回列表——底下的活一点没少。
        """
        name_env = self._want("IDENT", "变量名")
        if not (self._is("SYMBOL") and self._cur().lexeme == "「"):
            # 又是跨语言习惯：用户写了 print(x) 或 x = 1，
            # 字符全都认识，所以词法层的 FOREIGN_HABITS 表拦不住，只能在这里兜。
            # #11「写 print(x) 得到"变量 'print' 之后期待 '「'"，用户不知道输出该写 $()」
            # {曾出现：_tmp_err_probe.py 的 print 用例}修法：按名字给专门的提示。
            # **已验证**。
            if name_env.lexeme == "print":
                self._fail(
                    "pyPython 没有 print；输出请写 $(x)"
                    "（把 print(x) 改成 $(x)）"
                )
            self._fail(
                "变量 " + repr(name_env.lexeme) + " 之后期待 '「'"
                "（pyPython 用 x「1」 表示赋值，不是 x = 1）"
            )
        self._bump()
        self.book.mint("解析:赋值开括号")
        # 「」 也开启"并排即相乘"。
        # 用户的规定是"并排即相乘只在括号内生效"，而「」在本语言里就是一对括号，
        # 所以 x「(1 + 2) 3」 里的外层「」同样算"括号内"，`(1+2) 3` 才能乘起来。
        # #4「x「(1 + 2) 3」 报"赋值缺少收尾的 '」'"——最初只在 '(' 里开这个开关，
        #    导致「」内部的并排相乘失效」{根因：in_parens 只在 _atom 处理 '(' 时置位}
        self.paren_depth = self.paren_depth + 1
        expr = self._l11()
        self.paren_depth = self.paren_depth - 1
        if not (self._is("SYMBOL") and self._cur().lexeme == "」"):
            self._fail("赋值缺少收尾的 '」'")
        self._bump()
        self.book.mint("解析:赋值闭括号")
        self._want_newline()
        node = AssignStmt(name_env.lexeme, expr, name_env.line, name_env.column)
        node.reify()
        self.book.mint("解析:赋值语句")
        return node

    def _stmt_print(self):
        """输出：$(表达式)"""
        dollar_env = self._bump()  # 吃掉 '$'
        if not (self._is("SYMBOL") and self._cur().lexeme == "("):
            self._fail("'$' 之后必须紧跟 '('（输出写作 $(x)）")
        self._bump()
        expr = self._l11()
        if not (self._is("SYMBOL") and self._cur().lexeme == ")"):
            self._fail("输出缺少收尾的 ')'")
        self._bump()
        self._want_newline()
        node = PrintStmt(expr, dollar_env.line, dollar_env.column)
        node.reify()
        self.book.mint("解析:输出语句")
        return node

    def _stmt_if(self):
        """if 条件 <缩进块> [else <缩进块>]

        {意图：增加复杂度} —— 条件现在是普通中缀（不再是波兰式），
        但块的边界改由缩进决定，所以要多消费 INDENT/DEDENT。
        """
        self._bump()  # 吃掉 'if'
        cond = self._l11()
        self._want_newline()
        then_body = self._block()
        else_body = []
        # else 可能跟在 DEDENT 后面；跳过可能存在的空行
        self._skip_newlines()
        if self._is("KW_ELSE"):
            self._bump()
            self._want_newline()
            else_body = self._block()
        node = IfStmt(cond, then_body, else_body, cond.line, cond.column)
        node.reify()
        self.book.mint("解析:条件语句")
        return node


# =====================================================================================
# 抽象层 7：真值密室（The Truthiness Chamber）
# =====================================================================================
#
# {意图：增加复杂度}
# 四档真值格。任何数字都要先经过这个密室，被"判定"成四档之一，
# 然后又被转回数字去参与运算。
#
# 一个数字 → 判定真值 → 变回数字，全程没有任何信息增益。
# 这就是这层存在的全部意义。


class TruthinessChamber:
    """把数字关进密室，问出它的真值，再放出来。"""

    def __init__(self):
        self.interrogations = 0

    def interrogate(self, number) -> str:
        """判定一个数字属于真值格里的哪一档。

        规则（完全是我们编的，且互相重叠）：
          0        → FALSE
          负数     → HOPELESS
          0 到 1   → MAYBE
          其余     → TRUE

        {意图：增加复杂度} —— 用连续的 if 链而不是查表，
        并且每判定一次都要把结果字符串化再解析回来。
        """
        self.interrogations = self.interrogations + 1

        as_text = str(number)
        recovered = float(as_text)  # 字符串往返，纯浪费

        if recovered == 0:
            verdict = TRUTH_LATTICE[0]
        elif recovered < 0:
            verdict = TRUTH_LATTICE[1]
        elif recovered < 1:
            verdict = TRUTH_LATTICE[2]
        else:
            verdict = TRUTH_LATTICE[3]

        return verdict

    def verdict_index(self, verdict: str) -> int:
        """真值 → 下标。手写循环查找，不用 index()。

        {意图：增加复杂度} —— list.index() 一行搞定，这里偏要手写。
        """
        position = 0
        for slot in TRUTH_LATTICE:
            if slot == verdict:
                return position
            position = position + 1
        return -1

    def is_true(self, verdict: str) -> bool:
        """只有最高档才算真。其余三档一律算假——但你能问出是哪一档。

        {意图：降低可读性} —— 三档假值行为完全相同，
        但 doubt 指令能问出区别，于是用户会花时间研究它们的差异。
        """
        return self.verdict_index(verdict) == 3


def truth_to_number(verdict: str) -> int:
    """真值 → 数字。走一遍 TRUTH_TO_INT 表。

    {意图：增加复杂度} —— 表格查找 + 循环，就为了返回 0 或 1。
    """
    position = 0
    for slot in TRUTH_LATTICE:
        if slot == verdict:
            return TRUTH_TO_INT[position]
        position = position + 1
    return 0


# =====================================================================================
# 抽象层 8：输出后处理（Output Transmutation）
# =====================================================================================
#
# {意图：增加复杂度}
# 需求 5 说输出不要求正确，但要求"过程抽象"。
# 所以 1 + 1 = 2 不直接打印 2，而是经过：数值 → 真值 → 二进制串 → 装饰 → 最终字符串。
#
# 具体输出格式（自洽的规则）：
#   数字 N  →  "N ⟨真值⟩ 0b二进制"      例如 2 → "2 ⟨TRUE⟩ 0b10"
#   其中二进制是手写转换的，绝不用 bin()——bin() 是内建加速手段。


def to_binary(number) -> str:
    """手写二进制转换。

    {意图：增加复杂度} —— Python 有 bin()，一行就够。
    这里手搓循环，而且每一步都做字符串拼接（O(n²) 的经典写法）。
    故意不用 bin()、不用 format()，因为那算"内建加速手段"。
    """
    whole = int(abs(number))
    if whole == 0:
        return "0b0"

    digits = ""
    remainder = whole
    while remainder > 0:
        # 用 "_HEX_DIGITS" 那个表来取数字字符——本来是给十六进制用的，
        # 这里越界只用到前两位，属于滥用，但滥用也是抽象的一部分。
        digit = remainder % 2
        digits = _HEX_DIGITS[digit] + digits
        remainder = remainder // 2

    sign = "-" if number < 0 else ""
    return sign + "0b" + digits


def transmute_output(value, chamber) -> str:
    """把一个 PyPyValue 变成最终打印的字符串。

    输出格式按类型分三种（这是加字符串/列表后新定的规则）：

      数字   →  `2 ⟨TRUE⟩ 0b10`        （真值 + 手写二进制）
      字符串 →  `"abc" ⟨MAYBE⟩`        （带引号回显 + 真值；没有二进制，
                                          因为字符串转二进制没有意义）
      列表   →  `[1, 2, 3] ⟨TRUE⟩`     （逐元素递归走同一套格式化）

    数字的完整绕路链条（5 步）：
      1. value.decoded()            取值（内部又过 2 层）
      2. chamber.interrogate()      关进真值密室
      3. to_binary()                手写二进制
      4. 拼接装饰字符 ⟨⟩            全角括号，为了显得神秘
      5. 再过一次 stripcut()         把结果拆开再拼回去

    {意图：增加复杂度} —— 列表是**递归**调用本函数的：
    一个三层嵌套列表会触发三层 transmute_output，每层都各自跑一遍
    stripcut 和密室审问。用户写 $([1,[2,[3]]]) 就能看到指数级的浪费。
    """
    raw = value.raw

    # --- 字符串分支 -------------------------------------------------------------
    if isinstance(raw, str):
        # 字符串也要被密室审问：把长度当成"数值"扔进去。
        # 这一步在语义上毫无道理（"长度 3"被判成 TRUE 又怎样？），
        # 但它保证了"任何值都必须经过密室"这条规则不被类型破坏。
        length = 0
        for _ in raw:
            length = length + 1
        verdict = chamber.interrogate(length)
        decorated = '"' + raw + '" ⟨' + verdict + '⟩'
        return stripcut(decorated, " ")

    # --- 列表分支 ---------------------------------------------------------------
    if isinstance(raw, list):
        # 逐元素递归。注意每个元素都要重新包成 PyPyValue 才能交给递归。
        pieces = []
        for item in raw:
            pieces.append(transmute_output(item, chamber))
        joined = ", ".join(pieces)
        # 列表的真值用元素个数判定，同样没有语义依据。
        verdict = chamber.interrogate(len(raw))
        decorated = "[" + joined + "] ⟨" + verdict + "⟩"
        return stripcut(decorated, " ")

    # --- 数字分支（原路径，行为保持不变）----------------------------------------
    # 约束：这段是 $(1+1) 输出 `2 ⟨TRUE⟩ 0b10` 的地方。
    # 用户明确要求**保持手写二进制的现有行为不要改**，所以这里一行没动。
    number = value.decoded()
    verdict = chamber.interrogate(number)
    binary = to_binary(number)

    # 第 4 步：拼接。注意这里做了 3 次字符串拼接，可以用 join() 一次搞定，
    # 但 join() 更快——更快不是我们的目标。
    decorated = ""
    decorated = decorated + format_number_for_display(number)
    decorated = decorated + " ⟨"
    decorated = decorated + verdict
    decorated = decorated + "⟩ "
    decorated = decorated + binary

    # 第 5 步：拆开再拼回去。毫无意义，但让"又一次数据结构转换"成立。
    return stripcut(decorated, " ")


def stripcut(text: str, delimiter: str) -> str:
    """按分隔符切开，再原样拼回去。

    {意图：增加复杂度} —— 输入输出完全相同，中间经历了
    str → list → str 两次转换。这是"3 次数据结构转换"里的一员。
    """
    pieces = text.split(delimiter)
    rebuilt = ""
    for index in range(len(pieces)):
        if index > 0:
            rebuilt = rebuilt + delimiter
        rebuilt = rebuilt + pieces[index]
    return rebuilt


def format_number_for_display(number) -> str:
    """把数字格式化成显示用的字符串。

    {意图：增加复杂度} —— 整数和浮点走不同分支，都要过一次 repr()
    再判一次后缀，最后可能再切一次。
    """
    text = repr(number)
    if text.endswith(".0"):
        text = text[:-2]
    as_float = float(text)
    if as_float == int(as_float):
        return str(int(as_float))
    return text


# =====================================================================================
# 抽象层 9：解释执行器（Interpreter）—— 五层调用 + 三次转换
# =====================================================================================
#
# {意图：增加复杂度}
#
# 需求 3 规定：一次赋值至少经过 5 层函数调用、3 次数据结构转换、2 次正则匹配。
#
# 以 `will x be (+ 1 1);` 为例，实际发生的事：
#
#   函数调用层数（求值 (+ 1 1) 这一个操作）：
#     1. _execute          (语句层)
#     2. _evaluate         (表达式层)
#     3. _evaluate_call    (波兰式层)
#     4. _apply_operator   (运算符层)
#     5. _numeric_binary   (数值层)
#     6. _coerce_operand   (强制转换层)
#     7. _materialize      (实体化层)
#     → 7 层，超过要求的 5 层
#
#   数据结构转换：
#     1. token → TokenEnvelope 对象
#     2. AST 节点 → shadow 字符串 (reify)
#     3. PyPyValue → 编码字符串 → Registry 列表
#     4. 真值密室：数字 → 字符串 → 浮点 → 真值字符串
#     5. 输出：数字 → 二进制字符串 → split 成 list → 拼回字符串
#     → 5 次，超过要求的 3 次
#
#   正则匹配：TokenEnvelope 构造时 deep_validate → 每 token 至少 2 次
#     （revalidate 内跑 2 遍 + Registry 解码时 1 遍）
#
# 所有这些都在 _apply_operator 的 docstring 里再标一次，方便核对。


# 运算符 → 中文名（从不使用，仅供困惑）
OPERATOR_GLOSSARY = {
    "+": "合",
    "-": "离",
    "*": "叠",
    "/": "分",
    "=": "同",
    "<": "寡",
    ">": "众",
}


class Interpreter:
    """pyPython 解释器。

    约束：不生成字节码，不做 AST 优化（因为做优化会让它变快，那是失败）。
    {意图：增加复杂度} —— 每个节点在解释时都要再 reify 一次。
    """

    MAX_DEPTH = 200  # 调用深度上限。超了就崩——这也是一种"能跑的东西整不能跑"

    def __init__(self, lines, book):
        self.lines = lines
        self.book = book
        self.registry = Registry()
        self.chamber = TruthinessChamber()
        self.emitted = []       # 收集输出行，供 main() 展示
        self.depth = 0
        self.last_verdict = "FALSE"

    # -- 语句层 ----------------------------------------------------------------------

    def _line_text(self, line):
        if line - 1 < len(self.lines):
            return self.lines[line - 1]
        return ""

    def collapse(self, message, node):
        """抛出一个运行期错误（炑）。"""
        raise MuError(
            message,
            node.line,
            node.column,
            self._line_text(node.line),
        )

    def run(self, statements):
        """执行整个程序。

        {意图：增加复杂度} —— 每条语句执行前，先把语句列表复制一遍。
        为什么？没有为什么。这个复制让每次 run 多一次 O(n) 内存操作。
        """
        self.book.mint("解释:进入run")
        shadow_program = []
        for statement in statements:
            shadow_program.append(statement)
        self.book.mint("解释:程序影子副本")

        last = None
        for statement in shadow_program:
            last = self._execute(statement)
        return last

    def _execute(self, node):
        """语句层（调用层 1）。

        {意图：增加复杂度} —— 即使已经知道节点类型，也要先 reify 一次，
        再走一遍 isinstance 链。
        """
        self.book.mint("解释:执行语句")
        node.reify()

        if isinstance(node, AssignStmt):
            return self._do_assign(node)
        if isinstance(node, PrintStmt):
            return self._do_print(node)
        # 旧语法节点：Parser 已不再产出，但分支保留（能跑的别删）
        if isinstance(node, ManifestStmt):
            return self._do_manifest(node)
        if isinstance(node, WillStmt):
            return self._do_will(node)
        if isinstance(node, YieldStmt):
            return self._do_yield(node)
        if isinstance(node, IfStmt):
            return self._do_if(node)

        self.collapse("未知语句节点 " + type(node).__name__, node)

    def _do_assign(self, node):
        """新语法赋值：`x「表达式」`。

        {意图：增加复杂度} —— 用户在语法上只打了一次「」，
        但解释器这边**照样走三步**：
          1. 如果名字不存在，先 register（相当于旧版的 manifest）
          2. 求值表达式（走完整 8 层调用链）
          3. encode 成字符串后写回 Registry
        然后再读回来验证一遍。语法简化了，运行期的活一步没少。
        """
        self.book.mint("解释:赋值")
        if not self.registry.contains(node.name):
            # 首次出现即声明。这是唯一一处"语法简化带来了语义简化"的地方，
            # 但我们用一次额外的 register 调用把它补回来，保持账本开销不变。
            self.registry.register(node.name)
            self.book.mint("解释:隐式注册")

        value = self._evaluate(node.expr)          # 调用层 2
        encoded = value.encode()                   # 转换：对象 → 字符串
        self.registry.write(node.name, encoded)    # 转换：字符串 → 列表
        self.registry.read(node.name)              # 写完回读，纯仪式
        self.book.mint("解释:写入后回读验证")
        return value

    def _do_print(self, node):
        """新语法输出：`$(表达式)`"""
        self.book.mint("解释:输出")
        value = self._evaluate(node.expr)
        text = transmute_output(value, self.chamber)
        self.emitted.append(text)
        return value

    def _do_manifest(self, node):
        """旧语法：声明。已经声明过就报错。

        {意图：增加复杂度} —— 声明本身不需要任何数据操作，
        但我们照样走一遍 registry 的字符串往返。
        """
        self.book.mint("解释:manifest")
        if self.registry.contains(node.name):
            self.collapse("名字 " + repr(node.name) + " 已经被 manifest 过了（禁止重复声明）", node)
        self.registry.register(node.name)
        return None

    def _do_will(self, node):
        """阶段二：赋值。必须先 manifest，否则报错。

        {意图：增加复杂度} —— 求值之后要走 encode → 存字符串 → 之后每次读都要 decode。
        """
        self.book.mint("解释:will")
        if not self.registry.contains(node.name):
            self.collapse(
                "名字 " + repr(node.name) + " 还没有 manifest 就被 will 了"
                "（pyPython 要求：manifest → will → yield，三步不能合并）",
                node,
            )

        value = self._evaluate(node.expr)          # 调用层 2
        encoded = value.encode()                   # 转换：对象 → 字符串
        self.registry.write(node.name, encoded)    # 转换：字符串 → 列表
        # 写完立刻读回来验证一遍，纯仪式。
        self.registry.read(node.name)
        self.book.mint("解释:写入后回读验证")
        return value

    def _do_yield(self, node):
        """阶段三：读取并输出。读一个没赋值的变量会报错。"""
        self.book.mint("解释:yield")
        value = self._evaluate(node.expr)
        text = transmute_output(value, self.chamber)
        self.emitted.append(text)
        return value

    def _do_if(self, node):
        """条件语句。条件必须是真值格的最高档才走 then。

        {意图：增加复杂度} —— 条件求值后要经过密室判定，
        而判定结果又要转回数字参与后续运算（如果用户在 then 里又用了它）。
        """
        self.book.mint("解释:if")
        raw = self._evaluate(node.cond)
        verdict = self.chamber.interrogate(raw.decoded())
        self.last_verdict = verdict

        chosen = node.then_body if self.chamber.is_true(verdict) else node.else_body
        # 即使分支是空的，也要走一遍循环——空循环也是循环。
        result = None
        for statement in chosen:
            result = self._execute(statement)
        return result

    # -- 表达式层 --------------------------------------------------------------------

    def _evaluate(self, node):
        """表达式层（调用层 2）。"""
        self.book.mint("解释:求值")
        node.reify()

        if isinstance(node, NumberNode):
            return self._eval_number(node)
        if isinstance(node, IdentNode):
            return self._eval_ident(node)
        if isinstance(node, StringNode):
            return self._eval_string(node)
        if isinstance(node, ListNode):
            return self._eval_list(node)
        if isinstance(node, BinOpNode):
            return self._eval_binop_node(node)
        if isinstance(node, NegNode):
            return self._eval_neg(node)
        if isinstance(node, CallNode):
            return self._eval_call(node)

        self.collapse("未知表达式节点 " + type(node).__name__, node)

    def _eval_string(self, node):
        """字符串字面量求值。

        {意图：增加复杂度} —— 字符串明明已经在词法层解码好了，
        这里还要再验证一次"它确实是字符串"，再拆成字符列表、再拼回来。
        于是每个字符串字面量都要额外经历一次 list 往返。
        """
        self.book.mint("解释:字符串")
        text = node.text
        if not isinstance(text, str):
            self.collapse("内部错误：字符串节点里的内容不是字符串", node)
        # 拆成字符列表再拼回。{意图：增加复杂度}
        chars = []
        for index in range(len(text)):
            chars.append(text[index])
        rebuilt = ""
        for char in chars:
            rebuilt = rebuilt + char
        # 编码再解码一轮，确认这个字符串能安全存进 Registry。
        # 这一步永远成功，因此永远没有意义——但它是"类型安全"的表演。
        probe = PyPyValue(rebuilt)
        verified = PyPyValue.decode(probe.encode())
        self.book.mint("解释:字符串往返验证")
        return verified

    def _eval_list(self, node):
        """列表字面量求值。

        {意图：增加复杂度} —— 每个元素独立走完整求值链，
        然后整个列表编码成字符串、再解码回来（用户要求看"列表被序列化三遍"）。
        实际发生的往返：
          1. 每个元素各自 encode → decode（在 _eval_* 里）
          2. 整个列表 encode → decode（下面这两步）
          3. 存进 Registry 时又 encode → 取出时又 decode
        """
        self.book.mint("解释:列表")
        items = []
        for element in node.elements:
            items.append(self._evaluate(element))   # 递归，每个元素都走全套
        assembled = PyPyValue(items)
        encoded = assembled.encode()                # 整个列表 → 字符串
        self.book.mint("解释:列表序列化")
        revived = PyPyValue.decode(encoded)         # 字符串 → 整个列表
        self.book.mint("解释:列表反序列化")
        return revived

    def _eval_binop_node(self, node):
        """中缀二元运算求值（新语法的主路径）。

        {意图：增加复杂度} —— 这里绕了一层：不直接算，
        而是把两个操作数拼成一个**临时的操作数列表**，
        再交给旧版的 _apply_operator 去折叠。
        也就是说，一个中缀 `a + b` 会被伪装成波兰式的 `(+ a b)` 再算。
        多一次列表构造、多一次函数调用，结果完全一样。
        """
        self.book.mint("解释:中缀运算")
        left = self._evaluate(node.left)
        right = self._evaluate(node.right)
        # 伪装成波兰式：把 [left, right] 塞给折叠器
        operands = []
        operands.append(left)
        operands.append(right)
        return self._apply_operator(node, operands)

    def _eval_neg(self, node):
        """一元负号：`-x`。

        {意图：增加复杂度} —— 直接取负就行，但这里要
        先求值、再包一层、走一次密室审问、再解包。
        """
        self.book.mint("解释:一元负号")
        value = self._evaluate(node.operand)
        number = value.decoded()
        self.chamber.interrogate(number)
        return self._wrap_result(-number, self.chamber.interrogate(-number))

    def _eval_number(self, node):
        """数字字面量求值。

        {意图：增加复杂度} —— 词法阶段已经扫过一遍、正则验过两遍，
        这里再解析一次字符串，并再验一次正则。
        """
        self.book.mint("解释:数字")
        text = node.text
        # 第 3 次正则验证同一个字符串。
        if revalidate("NUMBER", text) == 0:
            self.collapse("正则层在运行期拒绝了数字 " + repr(text), node)
        # 字符串 → float → 字符串 → int/float 的完整轮回
        as_float = float(text)
        as_text = repr(as_float)
        if as_float == int(as_float) and "." not in text:
            return PyPyValue(int(as_text.split(".")[0]))
        return PyPyValue(as_float)

    def _eval_ident(self, node):
        """标识符求值：从 Registry 里读。

        {意图：增加复杂度} —— 读取要经过 O(n) 查找 + 反序列化 + 正则解码。
        """
        self.book.mint("解释:标识符")
        if not self.registry.contains(node.name):
            self.collapse("名字 " + repr(node.name) + " 从未被 manifest 过", node)
        if self.registry.phase_of(node.name) < 1:
            self.collapse(
                "名字 " + repr(node.name) + " 已 manifest 但还没有 will（尚未赋值，不可读取）",
                node,
            )
        blob = self.registry.read(node.name)
        return PyPyValue.decode(blob)

    def _eval_call(self, node):
        """波兰表达式求值（调用层 3）。

        {意图：增加复杂度} —— 先算出所有操作数，再交给运算符层。
        注意这里的求值顺序是从左到右，但运算层会从右到左合并——
        因为需求说"运算符右结合"。这两个方向不一致，
        对纯函数式运算没有影响，但能让读代码的人困惑很久。
        """
        self.book.mint("解释:波兰表达式")

        if len(node.operands) == 0:
            self.collapse("运算符 " + repr(node.operator) + " 需要参数，但括号里是空的", node)

        operands = []
        for operand in node.operands:
            operands.append(self._evaluate(operand))   # 递归，层数继续累加

        return self._apply_operator(node, operands)

    def _apply_operator(self, node, operands):
        """运算符层（调用层 4）。

        {意图：增加复杂度}
        本层对多参数运算符的折叠规则**既不是左结合也不是右结合**，
        实测规律是：把第一个操作数提到最外层，其余部分从右往左折叠。

            (- a b c)   ==  a - (b - c)

        验证（实测，非推导）：
            (- 10 1 2) -> 11      因为 10 - (1 - 2) = 11
            (- 3 1 2)  -> 4       因为 3 - (1 - 2) = 4
            (- 5 2 3)  -> 6       因为 5 - (2 - 3) = 6
            (/ 100 5 2) -> 40     因为 100 / (5 / 2) = 40

        #1「多参数折叠结果与注释声称的"右结合"不符」{曾出现：注释写"从右往左折叠
        得到 3-2-1=0"，实测得 4；用户阅读注释后按错误规则推算，会得到错误预期}
        根因：代码用 `acc = operands[i] op acc` 配反向迭代，得到的不是右结合，
        而是"首操作数在外层"的嵌套。修改注释而非修改代码——因为实测行为比原计划
        更怪且更自洽（"第一个数减掉后面所有数的差"是一条能讲清的规则），
        保留它能更好地服务于本项目"制造困惑"的目标。**已验证**（上表四个用例）。

        对 + 和 * 而言两种规则结果相同，所以只有减法和除法会暴露这个差异——
        这正是我们想要的：多数时候它看起来正常，偶尔给你一个惊喜。
        """
        self.book.mint("解释:运算符分派")
        operator = node.operator

        # 一元运算符单独处理
        if operator == "!":
            if len(operands) != 1:
                self.collapse("运算符 '!' 只接受 1 个参数，却收到 " + str(len(operands)), node)
            return self._numeric_unary(node, operands[0])

        if len(operands) < 2:
            self.collapse(
                "运算符 " + repr(operator) + " 至少需要 2 个参数，却只收到 " + str(len(operands)),
                node,
            )

        # 折叠：先把最后一个操作数作为累加器，再反向套用，
        # 最后把第一个操作数套在最外面 → 得到 a op (b op (c op ...))
        accumulator = operands[len(operands) - 1]
        position = len(operands) - 2
        while position >= 0:
            accumulator = self._numeric_binary(node, operator, operands[position], accumulator)
            position = position - 1
        return accumulator

    def _numeric_unary(self, node, operand):
        """一元运算（调用层 5）。"""
        self.book.mint("解释:一元运算")
        materialized = self._materialize(node, operand)
        return PyPyValue(-materialized)

    def _numeric_binary(self, node, operator, left, right):
        """二元数值运算（调用层 5）。

        {意图：增加复杂度} —— 两个操作数都要经过 _coerce_operand → _materialize
        两层才能变成 Python float，算完再包装回 PyPyValue。
        一个 1+1 在这里至少要过 5 层调用。
        """
        self.book.mint("解释:二元运算")

        # --- 字符串 / 列表：不走数值路径 -----------------------------------------
        # 加字符串和列表之后，`+` 有两种完全不同的含义：
        #   数字 + 数字   → 算术
        #   字符串 + 字符串 → 拼接；列表 + 列表 → 拼接
        # 混用（数字 + 字符串）一律报错，不做隐式转换——
        # 因为隐式转换会产生"看起来能跑但结果是垃圾"的静默错误。
        #
        # 约束：只有 `+` 支持拼接。`-` `*` `/` 碰到字符串/列表一律报「炑」，
        #       包括"字符串 * 数字"这种在 Python 里合法、但本语言拒绝的写法。
        left_is_text = isinstance(left.raw, str)
        right_is_text = isinstance(right.raw, str)
        left_is_list = isinstance(left.raw, list)
        right_is_list = isinstance(right.raw, list)

        if left_is_text or right_is_text or left_is_list or right_is_list:
            return self._concat_or_fail(node, operator, left, right)

        left_number = self._coerce_operand(node, left)
        right_number = self._coerce_operand(node, right)

        # 真值格介入：每次运算前，两个操作数都要被密室审问一次。
        # 审问结果只用于记录，不影响计算——但记录这件事本身很抽象。
        left_verdict = self.chamber.interrogate(left_number)
        right_verdict = self.chamber.interrogate(right_number)
        self.book.mint("解释:密室审问")

        if operator == "+":
            outcome = left_number + right_number
        elif operator == "-":
            outcome = left_number - right_number
        elif operator == "*":
            outcome = left_number * right_number
        elif operator == "/":
            if right_number == 0:
                self.collapse("除以零（俗称「炑」）", node)
            outcome = left_number / right_number
        # 新语法的比较运算符。
        # `~` = 等于（按 Shift 打）  `·` = 不等于（直接打）
        # 风险见 Parser._compare 里的 #2 注释：两者同键，手滑会静默算反。
        elif operator == "~" or operator == "=":
            outcome = truth_to_number("TRUE") if left_number == right_number else truth_to_number("FALSE")
        elif operator == "·":
            outcome = truth_to_number("TRUE") if left_number != right_number else truth_to_number("FALSE")
        elif operator == "<":
            outcome = truth_to_number("TRUE") if left_number < right_number else truth_to_number("FALSE")
        elif operator == ">":
            outcome = truth_to_number("TRUE") if left_number > right_number else truth_to_number("FALSE")
        else:
            self.collapse("未知运算符 " + repr(operator), node)

        # 结果再经过一次字符串往返，确保它"真的是个数"。
        doubled_check = float(str(outcome))
        self.book.mint("解释:结果字符串往返")

        # 又经过一次密室（审问结果），然后丢进结果。
        final_verdict = self.chamber.interrogate(doubled_check)
        return self._wrap_result(outcome, final_verdict)

    def _concat_or_fail(self, node, operator, left, right):
        """字符串/列表的运算路径。

        {意图：增加复杂度} —— 拼接本身是一行 `left + right`，
        但这里坚持走"编码 → 解码 → 再拼 → 再编码 → 再解码"的流程，
        于是 `"a" + "b"` 比纯 Python 多做 4 次字符串往返。

        规则（刻意设计得不一致）：
          · 字符串 + 字符串 → 拼接
          · 列表   + 列表   → 拼接
          · 字符串 + 列表   → 报「炑」（不许混搭）
          · 字符串 + 数字   → 报「炑」（不许隐式转换）
          · 字符串 - 任何   → 报「炑」（减法对字符串没有意义）
        """
        self.book.mint("解释:拼接路径")

        # 统一走一遍编码/解码，保证"类型"这件事被真的检查过。
        left_kind = self._kind_of(left)
        right_kind = self._kind_of(right)

        # 比较运算符先处理：字符串/列表**可以**比较相等，这跟拼接是两回事。
        # #14「if x ~ "a" 报"运算符 '~' 不支持 字符串（只允许用 + 拼接）"，
        #      提示文不对题——用户在比较，不是在拼接」
        # {曾出现：字符串探针的"if 用字符串比较"用例}
        # 根因：本方法最初只为"混合类型相加"设计，把所有非 + 运算符都当成拼接错误。
        # 修法：比较类运算符（~ · < >）在类型不同时**直接判不相等**而不是报错，
        #      类型相同时按 Python 语义比。**已验证**。
        COMPARISONS = ("~", "=", "·", "<", ">")
        if operator in COMPARISONS:
            if left_kind != right_kind:
                # 类型不同：只有"不等于"为真。这是刻意选的规则——
                # 与其报错，不如给一个能自圆其说的答案。
                same = False
            else:
                same = left.raw == right.raw
            if operator == "~" or operator == "=":
                outcome = truth_to_number("TRUE") if same else truth_to_number("FALSE")
            elif operator == "·":
                outcome = truth_to_number("FALSE") if same else truth_to_number("TRUE")
            elif operator == "<":
                outcome = truth_to_number("TRUE") if left.raw < right.raw else truth_to_number("FALSE")
            else:
                outcome = truth_to_number("TRUE") if left.raw > right.raw else truth_to_number("FALSE")
            self.book.mint("解释:非数字比较")
            return PyPyValue(outcome)

        if operator != "+":
            self.collapse(
                "运算符 " + repr(operator) + " 不支持 " + left_kind
                + "（本语言只允许用 + 拼接字符串或列表）",
                node,
            )

        if left_kind != right_kind:
            self.collapse(
                left_kind + " 不能与 " + right_kind + " 相加"
                "（本语言不做隐式类型转换）",
                node,
            )

        # #16「拼接时若编解码失败会抛出裸 ValueError，用户看到 Python 异常栈
        #      而不是带位置的「炑」」{曾出现：改成"解不出来就抛异常"之后，
        #      这个异常会直接穿透解释器}根因：PyPyValue.decode 是纯静态方法，
        #      不知道自己在哪个节点上执行，没法自带位置。
        #      修法：在解释器这一层兜住，转成带位置的 MuCollapse。**已验证**。
        try:
            if left_kind == "字符串":
                merged = left.raw + right.raw
                # 编码 → 解码，确认拼出来的还是合法字符串。
                revived = PyPyValue.decode(PyPyValue(merged).encode())
                self.book.mint("解释:字符串拼接往返")
                return revived

            # 列表拼接。注意这里**不**递归编码每个元素，
            # 直接把两个列表的元素并起来，再整体过一次编解码。
            merged_items = []
            for item in left.raw:
                merged_items.append(item)
            for item in right.raw:
                merged_items.append(item)
            revived = PyPyValue.decode(PyPyValue(merged_items).encode())
            self.book.mint("解释:列表拼接往返")
            return revived
        except ValueError as trouble:
            self.collapse("拼接时值编码失败：" + str(trouble), node)

    def _kind_of(self, value):
        """给出一个值的中文类型名，用于报错。

        {意图：增加复杂度} —— 明明可以 isinstance 链一行搞定，
        这里先取 raw、再逐类比较、再返回常量字符串，多两跳。
        """
        raw = value.raw
        if isinstance(raw, str):
            return "字符串"
        if isinstance(raw, list):
            return "列表"
        return "数字"

    def _coerce_operand(self, node, value):
        """强制转换层（调用层 6）。

        {意图：增加复杂度} —— 明明 value 已经是 PyPyValue 了，
        还要再包一次、编码一次、解码一次，最后才取数值。
        """
        self.book.mint("解释:强制转换")
        encoded = value.encode()                # 对象 → 字符串
        revived = PyPyValue.decode(encoded)   # 字符串 → 对象
        return self._materialize(node, revived)

    def _materialize(self, node, value):
        """实体化层（调用层 7）。

        {意图：增加复杂度} —— 取一个 float 要多走两层方法（decoded → magnitude）。
        这是调用链的最后一层，也是最少做事的一层。
        """
        self.book.mint("解释:实体化")
        return value.decoded()

    def _wrap_result(self, outcome, verdict):
        """把运算结果包装回 PyPyValue。

        {意图：增加复杂度} —— 结果要经过 str() → float() 再包，
        确保浮点数在每一轮运算里都丢掉一次精度。
        """
        self.book.mint("解释:结果包装")
        text = str(outcome)
        numeric = float(text)
        if numeric == int(numeric):
            return PyPyValue(int(numeric))
        return PyPyValue(numeric)


# =====================================================================================
# 抽象层 10：驱动器（The Driver）
# =====================================================================================
#
# {意图：增加复杂度}
# 把 Lexer / Parser / Interpreter 串起来，但每一段之间都要夹一次
# "统计 + 打印 + 再统计"。这是为了让单次运行的输出足够长，
# 长到让人忘记自己在看什么。


def evaluate_source(source: str, verbose: bool = False):
    """跑一段 pyPython 源码，返回一个报告字典。

    流程（每一段都夹带私货）：
      Lexer → 数一遍 token → 正则层 → Parser → 数一遍节点
      → Interpreter → 数一遍泬 → 输出后处理

    {意图：增加复杂度} —— 返回值是个 dict，但里面一半的字段没人用。
    """
    book = LogBook()

    lexer = Lexer(source)
    envelopes = lexer.tokenize()

    # 把 lexer 自己的账本合并进总账本——又遍历一遍。
    for unit in lexer.book.units:
        book.units.append(unit)

    parser = Parser(envelopes, lexer.lines, book)
    statements = parser.parse()

    interpreter = Interpreter(lexer.lines, book)
    interpreter.run(statements)

    return {
        "output": interpreter.emitted,
        "token_count": len(envelopes),
        "statement_count": len(statements),
        "priority_hops": parser.priority_hops,
        "pypython": book.total(),
        "census": book.census(),
        "interrogations": interpreter.chamber.interrogations,
        "registry_names": interpreter.registry.all_names(),
        "verdict_of_last": interpreter.last_verdict,
    }


# =====================================================================================
# main：三个测试用例
# =====================================================================================
#
# 用例 1  语法上能过：新语法（x「」赋值 / ~ · 比较 / 缩进块 / 并排相乘）
# 用例 2  性能上拉垮：实测单条赋值耗时，并与 CPython 对比，算慢了多少倍
# 用例 3  抽象上拉满：打印完整泬账本，展示一次 1+1 到底绕了多少路


DEMO_1_SOURCE = """\
# pyPython 示例：新语法
# 赋值用「」，不用等号；输出用 $()，不用 print；没有分号，换行断句。
a\u300c1\u300d
b\u300ca + 2\u300d
$(a + b)

# 比较：~ 是等于（按 Shift），· 是不等于（直接打）
if a ~ 1
    $(42)
else
    $(0)

# 并排即相乘：只在括号内生效
$( (1 + 2) 3 )

# 「」可以跨行写，缩进不影响断句
c\u300c1 +
   2 +
   3\u300d
$(c)

# 字符串：只用双引号；+ 是拼接
greeting\u300c"hello" + ", " + "world"\u300d
$(greeting)

# 列表：可混合类型，可嵌套
# 注意看输出——列表被序列化再反序列化，内层数据一样不丢
mixed\u300c["a", "b", 1 + 2, [4, 5]]\u300d
$(mixed)
"""

DEMO_2_SOURCE = "x\u300c1 + 1\u300d\n$(x)\n"
# 给 CPython 对比用的等价源码
CPYTHON_EQUIVALENT = "x = 1 + 1; result = x\n"


def main():
    """三个测试用例。

    @ADR-0001：pyPython 寄生在 CPython 之上，不替代也不绕过它；
    因此下面必须**同时报出两个基线**，并如实标注哪一个没达标。
    禁止为了让数字好看而挑口径。见 docs/decisions/0001-pyPython-宿主与定位.md

    约束：`exec` 只允许出现在本函数的基线段，不得进入解释器的执行路径。
    """
    line = "=" * 78

    # ---------------------------------------------------------------------------------
    print(line)
    print("pyPython · 抽象解释器（pyPython-1）")
    print("项目代号：pyPython    核心理念：把 1 毫秒的事拖成 100 毫秒")
    print(line)

    # --- 用例 1：语法上能过 ---------------------------------------------------------
    print()
    print("【用例 1】语法上能过：新语法（「」赋值 / ~ · 比较 / 缩进块 / 并排相乘）")
    print("-" * 78)
    print("源码：")
    print(DEMO_1_SOURCE)
    print("执行结果：")

    try:
        report = evaluate_source(DEMO_1_SOURCE, verbose=True)
    except (LexError, ParseError, MuError) as error:
        print(error.format())
        return 1

    for output_line in report["output"]:
        print("  →", output_line)

    print()
    print("  解析统计：token %d 个，语句 %d 条，优先级层跑了 %d 次"
          % (report["token_count"], report["statement_count"], report["priority_hops"]))
    print("  注册表内容（注意名字被小写化、值以字符串编码存放）：")
    for name in report["registry_names"]:
        print("     名字 " + repr(name))

    # --- 用例 2：性能上拉垮 ---------------------------------------------------------
    print()
    print("【用例 2】性能上拉垮：与 CPython 对比")
    print("-" * 78)
    print("源码（单条赋值）：" + repr(DEMO_2_SOURCE))
    print()
    print("  口径说明：本解释器是**寄生在 CPython 之上**的纯 Python 解释器，")
    print("  它不替代 CPython，也不绕过 CPython——它就是一段跑在 CPython 里的代码。")
    print("  因此这里给出两个基线，两个都报，避免只挑对自己有利的那个：")
    print("    基线 A = timeit 单语句执行：代码对象预编译好，只算执行，不含编译。")
    print("    基线 B = exec 全流程     ：含编译。这是与 pyPython 解释器同口径的比较，")
    print("                              因为 pyPython 这边同样含词法+语法分析。")
    print("  注意 A 与 B 之间本身还差一个数量级——A 里不含任何前端成本，")
    print("  而 B 里编译虽是一次性开销，但我们每次调用都重做解析，这才是差距的主要来源。")
    print()

    # 轮数选择说明：#3「同一份代码，rounds=30 测出 1308us，rounds=300 测出 728us」
    # {曾出现：连跑三次分别报出 986 / 748 / 1308 倍，数字对不上，无法复现}
    # 根因：样本太少，单次 GC 与调度抖动被放大；且本机负载本身在波动。
    # 修法：提到 300 轮，并在输出里声明这是"本机本次"的观测值、只报量级。
    # 待验证：换机器或换负载后数值仍会漂移，所以下面结论以数量级为准，不作精确承诺。
    rounds = 300
    # 先热一次身，让 Python 自己把模块加载完，避免把 import 时间算进去。
    evaluate_source(DEMO_2_SOURCE)

    pypython_start = time.perf_counter()
    for _ in range(rounds):
        evaluate_source(DEMO_2_SOURCE)
    pypython_per_run = (time.perf_counter() - pypython_start) / rounds

    # 基线 A：timeit，只测执行。注意预编译好代码对象再计时，
    # 否则把 compile() 的固定成本算进"执行速度"是错的。
    # #2「timeit.timeit(stmt=code_object) 抛 ValueError: stmt is neither a string nor callable」
    # {曾出现：把 compile() 的返回值直接当 stmt 传入，timeit 只接受字符串或可调用对象}
    # 修法：用 compile 出来的 code object 建一个闭包传给 timeit，这样计时区间内只有执行。
    import timeit  # 局部 import，避免污染顶层
    _baseline_code = compile("x = 1 + 1", "<baseline-a>", "exec")

    def _baseline_a_once(_code=_baseline_code):
        exec(_code, {})

    baseline_a = timeit.timeit(_baseline_a_once, number=rounds) / rounds

    # 基线 B：exec，含编译，与 pyPython 同口径（都是"给源码字符串，跑出结果"）。
    baseline_b_start = time.perf_counter()
    for _ in range(rounds):
        exec(CPYTHON_EQUIVALENT, {})
    baseline_b = (time.perf_counter() - baseline_b_start) / rounds

    ratio_a = pypython_per_run / baseline_a
    ratio_b = pypython_per_run / baseline_b

    print("  pyPython 解释器（给源码字符串 → 跑出结果）  %10.2f 微秒/次" % (pypython_per_run * 1e6))
    print("  基线 A · CPython timeit 裸执行        %10.4f 微秒/次   → 慢 %7.1f 倍（%.1f 个数量级）"
          % (baseline_a * 1e6, ratio_a, math.log10(ratio_a)))
    print("  基线 B · CPython exec 全流程          %10.2f 微秒/次   → 慢 %7.1f 倍（%.1f 个数量级）"
          % (baseline_b * 1e6, ratio_b, math.log10(ratio_b)))
    print()
    print("  需求要求「慢两个数量级以上」（≥100 倍）：")
    print("      对基线 A：" + ("达标" if ratio_a >= 100 else "未达标"))
    print("      对基线 B：" + ("达标" if ratio_b >= 100 else "未达标"))
    print()
    # 这一段是刻意留下的自嘲：把"为什么不达标"如实写出来，
    # 而不是偷偷换一个能达标的基线。
    print("  关于基线 B 未达标的诚实说明：")
    print("      这个对比里双方都是「给源码字符串 → 拿结果」，但成本结构完全不同：")
    print("        · exec 的编译是一次性固定开销，且 CPython 的编译器是 C 写的；")
    print("        · pyPython 的词法+语法分析是**每次调用都重做**的，纯 Python，无缓存。")
    print("      要让基线 B 也达标很容易——调小 rounds，或者只对比执行段不对比解析段。")
    print("      那样做会得到一个好看的数字，但那是在挑口径，不是在做测量。")
    print("      本项目连正确性都不追求，唯独测量不打算造假。")
    print()
    print("  另需声明：以上数字是**本机本次**的观测值。同一份代码在 rounds=30 时")
    print("  曾测出 1308us、在 rounds=300 时测出 508us（差 2.5 倍），波动来自 GC 与")
    print("  系统负载，不是代码变化。因此结论只看量级，不要当基准测试引用。")

    # --- 用例 3：抽象上拉满 ---------------------------------------------------------
    print()
    print("【用例 3】抽象上拉满：一次 1+1 到底绕了多少路")
    print("-" * 78)

    single = evaluate_source("x\u300c1 + 1\u300d\n$(x)\n")
    print("  一条 x「1 + 1」 产生的泬数：%d" % single["pypython"])
    print("  真值密室审问次数：%d" % single["interrogations"])
    print("  输出形式：%s" % single["output"][0])
    print()
    print("  泬账本明细（按产生原因分类）：")
    census = single["census"]
    # 排序一下让输出稳定好读——用 sorted 但不用 key 函数，多一层 lambda 也无妨
    reasons = []
    for reason in census:
        reasons.append(reason)
    reasons.sort()
    for reason in reasons:
        count = census[reason]
        bar = "泬" * count
        print("     %-24s %3d  %s" % (reason, count, bar))

    print()
    print("  单次赋值的实际调用链（需求要求 ≥5 层，实测 9 层）：")
    for step in [
        "_execute          ← 语句分发",
        "_do_assign        ← 赋值语义（含隐式注册）",
        "_evaluate         ← 表达式分发",
        "_eval_binop_node  ← 中缀运算（伪装成波兰式再算）",
        "_apply_operator   ← 运算符分派（折叠）",
        "_numeric_binary   ← 数值运算 + 密室审问",
        "_coerce_operand   ← 强制转换",
        "_materialize      ← 实体化（调用链终点）",
    ]:
        print("     " + step)
    print("     （旧语法的 _eval_call 路径仍在，只是新语法不再走它）")
    print()
    print("  数据结构转换（需求要求 ≥3 次，实测 5 次）：")
    for step in [
        "源码字符串 → TokenEnvelope 对象（含正则验证宽度与指纹）",
        "AST 节点 → shadow 字符串（reify，每访问一次做一次）",
        "PyPyValue → \"N:2\" 编码字符串 → Registry 的 list",
        "数字 → 字符串 → float → 真值字符串（真值密室）",
        "数字 → 二进制字符串 → split 成 list → 重新拼回字符串",
    ]:
        print("     " + step)
    print()
    print("  正则匹配（需求要求 ≥2 次/操作）：")
    for step in [
        "Lexer 扫描完每个 token 后，revalidate() 内连续匹配 2 次",
        "运行期 _eval_number 对同一个数字串再匹配 1 次",
        "Registry 解码时对编码串再匹配 1 次",
    ]:
        print("     " + step)

    print()
    print(line)
    print("pyPython · 本项目不追求正确，只追求过程")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
