# ADR-0004：IDE 寄生 IDLE，复用其装配流程，不改 idlelib 源码

- 状态：Accepted
- 记录日期：2026-02-14
- 决策依据：用户要求「把 Python 自带的 IDLE 源代码改装成 pyPython 的 IDE」；并在观察到手搓启动的缺陷后明确要求「你可以拉下 IDLE 的源代码，而不是手搓 IDE」
- 实施情况：已实施
- 关联记录：与 [ADR-0001](0001-pyPython-宿主与定位.md) 是同一思路在 IDE 上的应用

## 背景与证据

需求是三个功能：语法高亮、Tab 补全、语法提示。

第一版实现**手搓启动**：自己 `tk.Tk()`、自己 `EditorWindow(...)`、自己 `mainloop()`。
实测结果（`#I13`）——窗口能开、能编辑，但：

- 没有应用图标、没有 DPI 缩放（`fix_scaling` 未调用）
- 菜单栏行为残缺
- 标题显示 `*untitled (3.13.12)*`——把宿主 Python 版本号当成了语言版本
- 退出时报 `invalid command name .!menu.window`

读 `idlelib/pyshell.py` 的 `main()` 后确认，IDLE 的启动远不止"建个窗口"：
它还做 `fix_scaling`（DPI）、`fixwordbreaks`、图标加载、macOS 适配、
以及 `PyShellFileList` 的注册（决定"文件／最近文件／窗口"菜单是否可用）。
手搓等于把这些全部漏掉。

关键发现：IDLE 提供了**类属性形式的扩展点**。它的实始化代码写的是
`self.AutoComplete(...)` / `self.Calltip(...)` / `self.ColorDelegator`，
而窗口由 `FileList.EditorWindow` 创建——**都是可覆盖的类属性**，
不需要修改 idlelib 任何一个字节。

## 决策

1. **不手搓编辑器，也不修改 idlelib 的安装文件**。
   理由：改安装目录会在 Python 升级时全部丢失，并且会破坏原生 IDLE。
   全部改造通过**子类 + 类属性替换**完成，可逆、可卸载。
2. **启动流程复刻 `pyshell.main()` 的装配段**，而不是只建一个窗口。
   在装配前替换编辑器工厂：
   ```python
   pyshell.PyShellFileList.EditorWindow = PyPythonEditorWindow
   ```
   一处改动，"打开文件／新建／最近文件"全部自动用上 pyPython 编辑器。
3. **替换编辑器内三个组件工厂**：
   `AutoComplete` / `Calltip` / `ColorDelegator` 换成 pyPython 版本。
4. **运行不走 PyShell**。pyPython 没有 REPL 语义（只有语句，没有表达式求值），
   `>>>` 提示符会非常别扭。改为"整段运行 + 独立输出面板"（用户确认的方案）。
5. **不提供 while / 函数**等尚不存在的语法的高亮与提示**，
   宁少不滥**。关键字表只列 `if` / `else`。

## 备选方案

- **修改 idlelib 安装目录中的文件**：曾在第一版尝试过（改 `colorizer.py`）。
  否决理由：污染原生 IDLE，Python 升级后丢失，且难以回退。
- **完全自研 IDE，不依赖 IDLE**：否决。需求明确要求基于 IDLE 源码改装；
  且自研等于重写撤销、查找、缩进、括号匹配等全部编辑能力。
- **使用 PyShell 提供交互式 Shell**：用户在两个方案中选择了"整段运行"。
  理由已在决策第 4 条说明。
- **为 IDE 顺带给 pyPython 加 `while` 循环**：用户明确未选，本次不做。

## 后果与风险

收益：

- 免费获得 IDLE 的完整编辑能力：撤销、查找替换、缩进、括号匹配、行号、字体缩放。
- 改造**不修改任何 idlelib 文件**，Python 升级不会丢失改动。
- 窗口标题正确显示 `*untitled (pyPython)*`，不再误导用户。

成本与风险：

- **`#I11` / `#I12` / `#I14` / `#I18` 是同一类错误，共交了 4 次学费**：
  全都是"**改了一个看起来该改的名字，而真正被读的是另一个**"：

  | 以为要改的 | 实际生效的 |
  |---|---|
  | `make_pat()` | 模块加载时就算好了，此后没人再调 |
  | 模块级 `prog` | **`self.prog`**（构造时复制成实例属性） |
  | `FileList.EditorWindow` | **`PyShellFileList.EditorWindow`**（子类覆盖了） |
  | 模块级 `_windowlist` | **`registry.callbacks`**（实例属性） |

  四次的共性：**赋值合法、不抛异常、现象上看不出来**。
  唯一可靠的发现方式是**读源码找真正的读取点**，而不是猜哪个名字"应该"生效。
  这是修改本 IDE 时的首要注意事项。

- **`#I9` 高亮曾静默失效**：IDLE 的染色是"正则分组名 → tag 名"直接对应
  （`prog_group_name_to_tag.get(name, name)`），
  而 `tagdefs` 只定义了 8 个 tag。自造的分组名会 `tag_add` 到一个没配色的 tag，
  视觉上等于没染。**分组名必须原样写成已定义的 tag 名**。
  由于 tag 不够用，pyPython 特有符号**借用**了现有 tag：
  `「」$` → `BUILTIN`，数字 → `ERROR`（**数字显示为红色**，是 tag 不足的结果）。

- **`#I10` 自测曾假通过**：验证函数只检查"正则能否匹配"，
  不检查"tag 有没有真的贴上"，于是高亮全部失效时报 12/12 通过。
  现已改为读 `widget.tag_ranges()`——**验证最终效果，而非中间步骤**。

- **已知问题，非本项目引入**：退出时 stderr 可能出现
  `warning: callback failed in WindowList <TclError>: invalid command name ".!menu.window"`。
  经用**原生 IDLE** 复现确认，不装 pyPython、不碰本项目代码同样报此警告。
  它来自 `idlelib/window.py` 的回调在 mainloop 期间触发，属于 IDLE 自身的边界情况。
  **如实记录，不掩饰，也不假装是我们修好的。**

- **两份语法表**：IDE 侧另抄了一份关键字/符号表，与 `pypython.py` 的
  `KEYWORDS` 独立维护。语言改了而 IDE 没跟上时，高亮会与实际行为不一致。
  这是刻意的"两份真相"，但需要人工保持同步。

---

## 源码改造版遇到的同类问题（编号 #I20 起）

ADR-0005 的源码改造版（`pypython_idle/`）踩到的坑，编号沿用 `#I` 体系往下排。
前四条是**同一类错误在不同地方的复现**，第五条是验证方法本身的缺陷。

- **`#I20` 打开文件后高亮完全失效（严重，用户实测发现）**
  `editor.py` 的 `_addcolorizer()` 是 `if self.ispythonsource(filename):`
  **有条件地**创建高亮器；而 `ispythonsource()` 拿后缀比 `py_extensions`
  （`.py`/`.pyw`），`.pypy` 不在表里 → `self.color` 永远是 `None`。
  不报错，只是高亮没有 + `recolorize()` 抛 `AttributeError`。
  **新建窗口走不到这条路**（文件名为 `None` 时首个分支直接返回 `True`），
  所以只测新建发现不了。修法：覆盖 `ispythonsource` 无条件 `True`
  ——IDLE 自己对 Shell 窗口就是这么干的。

- **`#I21` `showtip()` 参数不足，每次按键喷 traceback（用户实测发现）**
  `calltip_w.py` 的签名是 `showtip(self, text, parenleft, parenright)`，
  改造 `calltip.py` 时只传了两个。后两个参数**不是装饰**：
  `checkhide_event()` 靠它们判断光标是否还在范围内。
  修法：范围定成整个当前行。

- **`#I22` 输出面板无限追加，看起来像"没输出"（用户实测发现）**
  面板从不清屏，每轮运行往后堆。用户看到的第一屏往往是**上一次**的结果。
  修法：每轮清屏 + 标注运行次数。

- **`#I23` 启动时往新窗口塞示例代码（用户实测发现）**
  新建文件就该是空的。示例与说明属于 README，不属于用户的编辑缓冲区。

- **`#I24` `idle.pyw` / `idle.bat` 会把原生 IDLE 拉起来**
  这两个文件指向系统 `idlelib` 与 `pyshell.main()`，却放在本项目包目录里，
  名字看起来像本项目的入口。已删除（确认无引用）。

- **`#I25` 差点把 Help 菜单弄坏（第 7 次"看起来没用、其实在用"）**
  准备把上游遗留文档（`help.html` / `CREDITS.txt` / `README.txt` 等 223 KB）
  挪进子目录，**先查引用才发现 `help.py` 与 `help_about.py` 真的会读它们**。
  已挪回原位。

- **`#I26` 验证只覆盖了"新建"，漏掉"打开文件"**
  最贵的一次：据 34/34 的通过率宣布"做完了"，而用户最常用的路径整个是坏的。
  **教训：验收必须覆盖所有入口路径，不能只测自己顺手的那条。**
  之后改为对 `new()` 和 `open()` **两条路径各跑一遍完整功能检查**。

## 受影响代码

- `pypython_ide.py` / `launch()`：复刻 IDLE 装配流程（`#I13` / `#I15`）
- `pypython_ide.py` / `_install_editor_factory()`：替换窗口与组件工厂（`#I14`）
- `pypython_ide.py` / `PyPythonColorDelegator`：改 `self.prog`（`#I11` / `#I12`）
- `pypython_ide.py` / `PYPYTHON_HILITE_PATTERN`：分组名必须等于 tag 名（`#I9`）
- `pypython_ide.py` / `_probe_highlight()`：验证真实 tag 区间（`#I10` / `#I26`）
- `pypython_ide.py` / `PyPythonAutoComplete`：`fetch_completions` 不走 rpc（`#I5`）
- `pypython_ide.py` / `PyPythonCalltip`：静态语法卡片，废弃 Python 文档（`#I2`）
- `pypython_ide.py` / `PyPythonEditorWindow.saved_change_hook()`：改标题（`#I16`）
- `pypython_ide.py` / `PyPythonScriptBinding`：F5 运行 + 输出面板
- `pypython.py` / `evaluate_source()`：IDE 唯一的调用入口
- `pypython_idle/pypython_editor.py` / `ispythonsource()`（`#I20`）
- `pypython_idle/calltip.py` / `open_calltip()`（`#I21`）
- `pypython_idle/runscript.py` / `show_output()`（`#I22`）
- `pypython_idle/startup.py` / `main()`（`#I23`）

## 变更记录

- 2026-02-14 建立。取代最初的"手搓启动 + 直接改 idlelib 文件"方案。
- 2026-02-14 补充"源码改造版遇到的同类问题"一节（`#I20`–`#I26`）。
