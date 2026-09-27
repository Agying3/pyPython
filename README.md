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
| **Tab** | 补全变量名 / 关键字(`if` `else` `「` `」` `$(`) |
| 打 `$(`, `「`, `"`, `[` | 弹出对应的 pyPython 语法卡片 |

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
```

**注意**:`~` 和 `·` 在同一个键上。打反了**不会报错**(两个都是合法运算符),
只会算错。这是已知设计,见 `docs/decisions/0002`。

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
examples/hello.pypy      可运行示例
docs/decisions/          架构决策记录
```

**注意**:`pypython_idle/` 里的 `help.html` / `CREDITS.txt` / `README.txt` /
`ChangeLog` 等文件**不能挪走** —— `help.py` 和 `help_about.py` 会在运行时读它们
(菜单的 Help / About 靠这个)。看着像没用的上游遗留,其实在用。

## 决策记录

改这个 IDE 之前建议先读 `docs/decisions/`:

- **0004** IDE 为什么寄生 IDLE 而不是手搓,以及 `#I1`–`#I26` 问题记录
- **0005** 两版为什么并存,以及改造踩过的坑

其中最重要的一条经验:改这个代码库时,**"看起来该改的名字"常常不是真正被读的那个**。
已经栽过 7 次(`make_pat` / 模块级 `prog` / `FileList.EditorWindow` /
`_windowlist` / `trans` 表 / `_chew_ordinaryre` / Help 用的 `help.html`),
每次都不报错。**读源码找真正的读取点,不要猜。**

第二条经验:**验收必须覆盖所有入口路径**。曾经只测"新建窗口"就宣布完成,
而"打开文件"那条路的高亮整个是坏的 —— 那是用户最常用的路径。
