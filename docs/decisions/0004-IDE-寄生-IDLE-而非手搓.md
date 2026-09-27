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

## 受影响代码

- `pypython_ide.py` / `launch()`：复刻 IDLE 装配流程（`#I13` / `#I15`）
- `pypython_ide.py` / `_install_editor_factory()`：替换窗口与组件工厂（`#I14`）
- `pypython_ide.py` / `PyPythonColorDelegator`：改 `self.prog`（`#I11` / `#I12`）
- `pypython_ide.py` / `PYPYTHON_HILITE_PATTERN`：分组名必须等于 tag 名（`#I9`）
- `pypython_ide.py` / `_probe_highlight()`：验证真实 tag 区间（`#I10`）
- `pypython_ide.py` / `PyPythonAutoComplete`：`fetch_completions` 不走 rpc（`#I5`）
- `pypython_ide.py` / `PyPythonCalltip`：静态语法卡片，废弃 Python 文档（`#I2`）
- `pypython_ide.py` / `PyPythonEditorWindow.saved_change_hook()`：改标题（`#I16`）
- `pypython_ide.py` / `PyPythonScriptBinding`：F5 运行 + 输出面板
- `pypython.py` / `evaluate_source()`：IDE 唯一的调用入口

## 变更记录

- 2026-02-14 建立。取代最初的"手搓启动 + 直接改 idlelib 文件"方案。
