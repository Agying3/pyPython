# pyPython IDE

## 怎么打开

在项目根目录 `H:\pyPython` 下,任选一条:

```
python pypython_idle_start.py                开一个空白编辑器
python pypython_idle_start.py 你的文件.pypy   打开指定文件
python -m pypython_idle                       等价,需要先 cd 到项目根
```

**推荐第一条** —— 它不要求当前目录在哪,直接跑就行。

启动后应该看到:

- 一个**空白**编辑器窗口,标题 `untitled (pyPython)` —— 就是新建文件的样子
- 菜单栏跟 IDLE 一样
- **没有**输出面板(跑完代码之后才会出现)

标题里的 `pyPython` 是替掉宿主 Python 版本号的位置。原版 IDLE 这里写 `3.13.12`,
容易让人以为自己在写 Python。

想看点东西跑起来,把 `examples/hello.pypy` 的内容复制进去,或者:

```
python pypython_idle_start.py examples\hello.pypy
```

## 三个功能怎么用

| 操作 | 效果 |
|---|---|
| **F5** | 运行编辑器里的全部代码,结果显示在输出面板(面板这时才出现) |
| **Tab** | 补全变量名 / 关键字 / 类名 / 函数名(`if` `while` `for` `def` `class` `「` `」` `$(`) |
| 打 `$(`, `「`, `"`, `[` | 弹出对应的 pyPython 语法卡片 |
| 在 `while`/`for`/`def`/`class` 行尾按回车 | 自动缩进一层 |

## 语言速查

```
a「1」              赋值(用 「」 代替等号,变量自动创建)
$(a)               输出(用 $() 代替 print)
~  ·               等于 / 不等于(同一个键,中文输入法下容易打反)
>  <               大于 / 小于
(a + b) 2          并排即相乘 = (a+b)*2,只在括号内生效
[1, [2], "x"]      列表,可嵌套可混类型
"abc" + "def"      字符串拼接,只能用双引号
if a ~ 1           缩进划块,没有冒号,没有分号
    $(42)
else
    $(0)

中文「42」           变量名可以用中文
$(中文)
```

### 第二版新增:循环、遍历、函数、类

```
while i < 3        循环
    i「i + 1」

for v in [1, 2]    遍历。可以遍历列表、字符串、字典,没有 range()
    $(v)

def 加(a, b)        函数。参数没有默认值
    return a + b
$(加(3, 4))         输出 7

def 数到(n)          可以递归,但有深度上限(120 层)
    if n < 1
        return 0
    return 数到(n - 1)

class 点            类
    def __init__(x, y)      构造器叫 __init__
        self.x「x」           self 不用写进参数表
    def 长度()               照 Python 习惯写 self 也行
        return self.x + self.y
p「点(1, 2)」        直接调类名就是建对象
$(p.长度())          输出 3
```

### 第三版新增:下标、字典、逻辑运算、循环控制

```
xs[0]  xs[-1]      下标。列表按位置,-1 是最后一个
xs[1]「99」         下标也能赋值
m[0][1]            下标可以嵌套

{「"a"」: 1}        字典。key 用 「」 包起来,冒号是本语言唯一的冒号用法
d「{}」             空字典
d["a"]             按 key 取值(没有这个 key 会报错)
d["b"]「2」         新增一项

a and b           逻辑运算用单词,不用 && || !
a or b             会短路,返回决定结果的那个操作数
not a              (不是 1/0)

break              跳出最内层循环。只能写在循环里,写在循环外解析期就报错
continue           跳到下一轮。函数体里的 break 不会打断调用方的循环
```

**`return` 可以省略**(省略时返回 0)。
**仍然没有**:切片、`while ... else`、异常、`lambda` / `import`、继承、`range()`。
字符串也不能用 `[]` 取字符(想按字符走请用 `for c in "..."`)。

**作用域按 Python 来**:函数里赋值默认建**局部**变量(所以递归正常),
想改全局要显式声明:

```
g「1」
def 改()
    全局 g「999」
改()
$(g)               输出 999
```

改语言之前**必读** `docs/decisions/0007` 与 `0008` ——
关键字表在 8 个地方各有一份,漏改一处不会报错,只会静默失效。

第三版起这几张表**语义分叉**了,不能无脑同步:

- `and` / `or` / `not` 要**高亮和补全**,但**绝不能**进
  `STATEMENT_KEYWORDS`(否则 `if not x` 会被当成新语句开头)
- `break` / `continue` 要**高亮和补全**,但**绝不能**进
  `PYPYTHON_BLOCK_OPENERS`(否则写完 `break` 按回车会多缩进一级)
- `break` / `continue` **反而必须**进 `pyparse._closere`(它们是块结束语句)

`tests/test_keyword_sync.py` 会逐项检查这些,包括反向断言("某某不该在哪张表里")。

**注意**:`~` 和 `·` 在同一个键上。打反了**不会报错**(两个都是合法运算符),
只会算错。这是已知设计,见 `docs/decisions/0002`。

变量名支持中文,也支持 `_` 和数字(不能数字开头)。见 `docs/decisions/0006`。

## 两个 IDE 版本

项目里有两套 IDE 实现,**都能用,互不冲突**:

| 版本 | 启动方式 | 说明 |
|---|---|---|
| **源码改造版** | `python pypython_idle_start.py` | 把 IDLE 源码抓进项目改的,不依赖系统 IDLE |
| 运行时代理版 | `python pypython_ide.py` | 单文件,运行时替换 IDLE 的类属性 |

改造版更彻底(自带全部 IDLE 源码),代理版更轻(单文件)。

## 已知问题

启动和退出时,stderr 可能出现:

```
warning: callback failed in WindowList <class '_tkinter.TclError'>:
invalid command name ".!menu.window"
```

**这不是本项目引入的。** 已用**原生 IDLE** 复现确认:
不装 pyPython、不碰本项目任何代码,原生 IDLE 同样报这条警告。
它来自 `idlelib/window.py` 的窗口列表回调,属于 IDLE 自身的边界情况。

**其他已知限制:**

- `·`(不等于)和 `~`(等于)在同一个键上。**打反了不报错**,只会算错
- 统计里的 `verdict_of_last` 是"最后一个 `if` 的判定",不是"最后输出的真假"。
  程序里没写 `if`,它就一直显示 `FALSE`
- 从文件打开**只认编码是 UTF-8** 的源文件(跟 IDLE 原版一致)

## 目录说明

```
pypython.py              解释器本体(与 IDE 无关,可单独用)
pypython_idle/           源码改造版 IDE(60 个模块从 idlelib 抓来改造)
  startup.py               启动装配(复刻 pyshell.main 但不开 Shell)
  pypython_editor.py       主编辑器窗口
  colorizer.py             语法高亮(已改造)
  autocomplete.py          Tab 补全(已改造)
  calltip.py               语法提示(已改造)
  pyparse.py               自动缩进(已改造)
  runscript.py             F5 运行(已接 pyPython 解释器)
  upstream-docs/           (无此目录)上游文档必须留在包根,见下
pypython_ide.py          运行时代理版 IDE
interpreter.py           早期的正经计算器解释器(已搁置)
examples/hello.pypy      可运行示例(含第一二版全部新语法 + 第三版)
tests/                   回归测试,`python tests/run_all.py` 一把跑完(10 个脚本)
docs/decisions/          架构决策记录
```

**注意**:`pypython_idle/` 里的 `help.html` / `CREDITS.txt` / `README.txt` /
`ChangeLog` 等文件**不能挪走** —— `help.py` 和 `help_about.py` 会在运行时读它们
(菜单的 Help / About 靠这个)。看着像没用的上游遗留,其实在用。

## 决策记录

改这个 IDE 之前建议先读 `docs/decisions/`:

- **0002** 语言为什么长这样(语法简化,实现不简化)
- **0004** IDE 为什么寄生 IDLE 而不是手搓,以及 `#I1`–`#I26` 问题记录
- **0005** 两版为什么并存,以及改造踩过的坑
- **0007** 第二版语言构造(while/for/def/class),以及 6 份关键字副本的同步清单

其中最重要的一条经验:改这个代码库时,**"看起来该改的名字"常常不是真正被读的那个**。
已经栽过 8 次(`make_pat` / 模块级 `prog` / `FileList.EditorWindow` /
`_windowlist` / `trans` 表 / `_chew_ordinaryre` / Help 用的 `help.html` /
`RE_IDENT` 与扫描器不一致),
每次都不报错。**读源码找真正的读取点,不要猜。**

第二条经验:**验收必须覆盖所有入口路径**。曾经只测"新建窗口"就宣布完成,
而"打开文件"那条路的高亮整个是坏的 —— 那是用户最常用的路径。

第三条经验:**API 反复测不出预期时,先怀疑自己的调用姿势**。
第二版开发中 `is_block_opener()` 连试三种参数都返回 `False`(连 `if` 都是),
看着像产品坏了,实际是测试喂错了 offset。改用真实编辑器端到端验证后立刻通过。
另外还有三处"失败"其实是测试自己写错了(构造器少一个下划线等)。
**报告失败之前,先确认测试测的是不是你以为的那件事。**
