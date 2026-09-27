"""pyPython IDE 的启动装配。

本文件由 IDLE 的 pyshell.main() 改造而来，**保留装配流程，砍掉 Shell**。

# [pyPython 改造] 为什么自己写一个而不直接用 pyshell.main()：
#
# pyshell.py 有 1699 行，其中绝大部分是 pyPython 用不上的东西：
#   · ModifiedInterpreter —— 通过 rpc 把代码送进**子进程**执行
#   · spawn_subprocess / restart_subprocess / kill_subprocess
#   · 调试器、栈查看器、断点管理
#   · PyShell 交互式 Shell（>>> 提示符、readline、历史、补全）
#
# pyPython 不需要子进程（它就是个同进程的函数调用），也不需要 Shell
#（它每次重新解析整段源码，没有"输入一句立刻求值"这回事，
#  套 >>> 提示符只会误导用户）。见 docs/decisions/0004。
#
# 所以这里**复刻 pyshell.main() 的装配段**——Tk root、DPI 缩放、图标、
# 字体断词、X11 粘贴、PyShellFileList、macOS 适配——但不开 Shell。
#
# 代价：这跟上游是**两份代码**。Python 升级改了上游，我们这份不会跟着变，
# 会慢慢漂移。这是刻意的取舍，与 ADR-0001 的"寄生"定位一致。
"""
import os
import sys

from tkinter import Tk, TclError, PhotoImage

from .config import idleConf
from .editor import fixwordbreaks
from .filelist import FileList
from .macosx import isAquaTk, setupApp
from .pyshell import PyShellFileList, fix_x11_paste
from .run import fix_scaling

# 模块级引用，与上游保持一致——有些代码会去读 pyshell.flist / pyshell.root。
flist = None
root = None


def install_editor_factory():
    """把 IDLE 的编辑器工厂换成 pyPython 的。

    # 关键：IDLE 有**两层**文件列表类，各自覆盖了 EditorWindow：
    #     class FileList:          EditorWindow = EditorWindow
    #     class PyShellFileList(FileList):  EditorWindow = PyShellEditorWindow
    # 我们实际实例化的是 PyShellFileList，所以**必须改子类那一份**；
    # 只改父类的会被子类属性压住，症状是"窗口还能开，但高亮/提示全没生效"，
    # 而且不报任何错。
    #
    # 这个坑在原型的实现里踩过一次（见 docs/decisions/0004 的 #I14），
    # 这里一并记录，避免重复。
    #
    # 约束：这是**全局**修改。改了之后同一进程里再开原生 IDLE 窗口
    # 也会用 pyPython 编辑器。因为我们整个进程就是 pyPython IDE，所以无妨；
    # 若要"两种窗口并存"，得改成按 flist 实例区分。
    """
    from .editor import EditorWindow
    from . import pypython_editor

    factory = pypython_editor.PyPythonEditorWindow
    FileList.EditorWindow = factory
    PyShellFileList.EditorWindow = factory
    return factory


def make_root():
    """建 Tk 主窗口并做全套初始化。

    顺序与 pyshell.main() 一致，因为其中几步有依赖关系：
    fix_scaling 要在建窗后立刻做（DPI），fixwordbreaks 要在文本控件
    创建前做（否则字体断词规则不生效）。
    """
    # NoDefaultRoot 让 tkinter 不再自动创建一个隐藏的默认 root。
    # 上游只在"使用子进程且非测试"时才调；我们没有子进程，
    # 但同样不希望多出一个隐藏窗口，所以无条件调。
    try:
        from tkinter import NoDefaultRoot
        NoDefaultRoot()
    except ImportError:
        pass

    global root
    root = Tk(className="pyPythonIdle")
    root.withdraw()

    fix_scaling(root)
    _set_icon(root)
    fixwordbreaks(root)
    try:
        fix_x11_paste(root)
    except Exception:
        # X11 粘贴是 Linux 专属；Windows/macOS 上失败无所谓。
        pass
    return root


def _set_icon(tk_root):
    """设置窗口图标，复用 IDLE 自带的图标文件。

    约束：找不到图标时**静默跳过**，不能因为图标缺失就让 IDE 起不来。
    """
    from platform import system

    icon_directory = os.path.join(os.path.dirname(__file__), "Icons")
    if not os.path.isdir(icon_directory):
        return
    try:
        if system() == "Windows":
            icon_file = os.path.join(icon_directory, "idle.ico")
            if os.path.exists(icon_file):
                tk_root.wm_iconbitmap(default=icon_file)
        elif not isAquaTk():
            from tkinter import TkVersion
            if TkVersion >= 8.6:
                ext, sizes = ".png", (16, 32, 48, 256)
            else:
                ext, sizes = ".gif", (16, 32, 48)
            files = [os.path.join(icon_directory, "idle_%d%s" % (size, ext))
                     for size in sizes]
            files = [f for f in files if os.path.exists(f)]
            if files:
                icons = [PhotoImage(master=tk_root, file=f) for f in files]
                tk_root.wm_iconphoto(True, *icons)
    except Exception:
        pass


def make_file_list(tk_root):
    """建文件列表。

    PyShellFileList 会注册"窗口"菜单、最近文件等——这正是我们
    复用它而不是自己写一个的原因（自带的好处）。
    """
    global flist
    flist = PyShellFileList(tk_root)
    setupApp(tk_root, flist)
    return flist


def open_editor(filename=None, flist=None):
    """打开（或新建）一个 pyPython 编辑器窗口。"""
    if flist is None:
        flist = globals()["flist"]
    if filename:
        editor = flist.open(filename)
        if editor is not None:
            return editor
    editor = flist.new()
    return editor


def main(argv=None):
    """pyPython IDE 主入口。

    与 pyshell.main() 的差异：
      · 不解析 -c/-r/-s/-t/-n 等 Shell 相关开关（那都是给子进程/Shell 用的）
      · 只接受"打开哪些文件"
      · 不开 Shell 窗口
    """
    if argv is None:
        argv = sys.argv[1:]

    filenames = [a for a in argv if not a.startswith("-")]

    # 按上游做法把 cwd 加入 sys.path，这样用户 import 同目录模块能成功。
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    install_editor_factory()

    tk_root = make_root()
    file_list = make_file_list(tk_root)

    opened = []
    for filename in filenames:
        if not os.path.exists(filename):
            print("\u627e\u4e0d\u5230\u6587\u4ef6\uff1a" + filename)
            continue
        editor = file_list.open(filename)
        if editor is not None:
            opened.append(editor)

    if not opened:
        # 新建一个空白编辑器。
        #
        # [修正] 这里原本会往新窗口里 insert SAMPLE_PROGRAM（一段示例代码），
        # 还会强改标题、弹一段欢迎说明。用户指出"打开后怎么不是空白的"——
        # 那是错的：**新建文件就该是空的**，跟任何编辑器一样。
        # 示例代码和用法说明属于 README 的内容，不该塞进用户的编辑缓冲区
        # （用户想保存的话，还得先把这段不是我写的代码删掉）。
        editor = file_list.new()
        opened.append(editor)

    tk_root.mainloop()

    try:
        tk_root.destroy()
    except Exception:
        pass
    return 0
