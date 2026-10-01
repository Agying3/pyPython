# IDE 使用

pyPython 有**两套 IDE 实现**，都能用，互不冲突。

| 版本 | 启动方式 | 特点 |
|---|---|---|
| **源码改造版**（推荐） | `python pypython_idle_start.py` | 把 IDLE 源码抓进项目改造，不依赖系统 IDLE |
| 运行时代理版 | `python pypython_ide.py` | 单文件，运行时替换 IDLE 的类属性 |

---

## 源码改造版（推荐）

### 怎么开

```
python pypython_idle_start.py                开一个空白编辑器
python pypython_idle_start.py 你的文件.pypy   打开指定文件
```

**推荐第一条**——它不要求当前目录在哪，直接跑就行。
（它只是把项目根塞进 `sys.path`，然后调 `pypython_idle.startup.main()`。）

### 启动后应该看到什么

- 一个**空白**编辑器窗口，标题 `untitled (pyPython)`
- 菜单栏跟 IDLE 一样
- **没有**输出面板（按 F5 跑完代码之后才会出现）

标题里的 `pyPython` 是替掉宿主 Python 版本号的位置。原版 IDLE 这里写
`3.13.12`，容易让人以为自己在写 Python。

### 三个功能

| 操作 | 效果 |
|---|---|
| **F5** | 运行编辑器里的全部代码，结果显示在输出面板（面板这时才出现） |
| **Tab** | 补全变量名 / 关键字 / 类名 / 函数名 |
| 打 `$(` `「` `"` `[` | 弹出对应的 pyPython 语法卡片 |
| 在 `if`/`while`/`for`/`def`/`class` 行尾按回车 | 自动缩进一层 |

### 语法提示卡片

打字时会弹出卡片。打 `$(` 告诉你输出怎么写，打 `未知` 告诉三值逻辑的规则。

可以试试打这三个：

```
$(
「
未知
```

---

## 运行时代理版

```
python pypython_ide.py
```

单文件 982 行。它**不复制 IDLE 源码**，而是在运行时替换掉 IDLE 的类属性
（关键字表、配色器、补全表等）。

改造版更彻底（自带全部 IDLE 源码），代理版更轻（单文件）。

---

## 为什么是"寄生 IDLE"

因为**手搓一个 IDE 是重复劳动**，而 IDLE 已经提供了：

- 多窗口管理、菜单、快捷键
- 编辑器组件、撤销栈、搜索替换
- 语法高亮框架（`ColorDelegator`）
- 自动缩进框架（`pyparse`）
- 补全框架（`autocomplete`）
- 调用提示框架（`calltip`）

改造的工作量集中在**换掉语言相关的那几张表**，而不是重写编辑器。
详见 [ADR-0004](https://github.com/Agying3/pyPython/blob/master/docs/decisions/0004-IDE-寄生-IDLE-而非手搓.md)。

### 代价：关键字表被抄成了 9 份

IDLE 原来的设计是"每种语言一个 `idlelib` 目录"，所以关键字表散落在各模块里。
本项目**继承了这种散落**，于是同一个关键字表在 9 个地方各有一份：

| 位置 | 作用 | `未知` 要加吗 |
|---|---|---|
| `pypython.py` `KEYWORDS` | 词法层 | **要** |
| `pypython.py` `STATEMENT_KEYWORDS` | 能否开一条语句 | **不要** |
| `pypython_idle/__init__.py` | 权威表 | **要** |
| `colorizer.py` | 高亮 | **要** |
| `hyperparser.py` | 光标判定 | **要** |
| `autocomplete.py` | Tab 补全 | **要** |
| `calltip.py` | 语法卡片 | **要** |
| `pyparse.py` `PYPYTHON_BLOCK_OPENERS` | 自动缩进 | **不要** |
| `pypython_ide.py` | 代理版 IDE | **要** |

**漏改一处不会报错，只会静默失效**——新关键字不高亮、不补全、或者
写完按回车多缩进一级。

所以 `tests/test_keyword_sync.py` 会逐项检查，**包括反向断言**
（"某某不该在哪张表里"）。

### 为什么有的"要"有的"不要"

这几张表**语义分叉**了，不能无脑同步：

- `and` / `or` / `not` 要**高亮和补全**，但**绝不能**进 `STATEMENT_KEYWORDS`
  （否则 `if not x` 会被当成新语句开头）
- `break` / `continue` 要**高亮和补全**，但**绝不能**进
  `PYPYTHON_BLOCK_OPENERS`（否则写完 `break` 按回车会多缩进一级）
- `break` / `continue` **反而必须**进 `pyparse._closere`（它们是块结束语句）
- `未知` 要**高亮和补全**，但**绝不能**进 `STATEMENT_KEYWORDS`
  （它是**值**，不是语句，加进去会破坏 `if 未知`）

---

## 已知问题

启动和退出时，stderr 可能出现：

```
warning: callback failed in WindowList <class '_tkinter.TclError'>:
invalid command name ".!menu.window"
```

**这不是本项目引入的。** 已用**原生 IDLE** 复现确认——不碰本项目任何代码，
原生 IDLE 同样报这条。它来自 `idlelib/window.py` 的窗口列表回调，
属于 IDLE 自身的边界情况。

不影响使用，也不影响退出码。

---

## 上游文档不能挪走

`pypython_idle/` 里的 `help.html` / `CREDITS.txt` / `README.txt` / `ChangeLog`
等文件**必须留在包根**——`help.py` 和 `help_about.py` 会在运行时读它们
（菜单的 Help / About 靠这个）。

看着像没用的上游遗留，其实在用。挪走了 Help 菜单就坏了。
